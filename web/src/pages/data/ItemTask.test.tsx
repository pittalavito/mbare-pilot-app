import { notifications } from "@mantine/notifications";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";

/** Blocco 08: an item's agent task (badge, «🤖» menu) and the items checked when a task gets «done». */

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const task = (name: string, title: string, status: string) => ({
  name, title, status, type: "development", objective: "o", context: "", criteria: [{ text: "c", done: false }], constraints: "", references: [],
});
const NOTE_TASK = task("agent-task-note.md", "Note", "to_verify");
const ACTIVITY = {
  name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", description: "", learned: "", references: [],
  items: [
    { text: "Note", done: false, priority: null, due: null, agent_task: NOTE_TASK.name },
    { text: "Tag", done: false, priority: null, due: null, agent_task: null },
  ],
  agent_tasks: [NOTE_TASK.name],
};

function api() {
  let tasks = [NOTE_TASK];
  const created = vi.fn(async (request: Request) => {
    const body = await request.json();
    const made = { ...task("agent-task-tag.md", "Tag", "created"), type: body.type };
    tasks = [...tasks, made];
    return made;
  });
  const saved = vi.fn(async (request: Request) => ({
    ...(await request.json()), name: NOTE_TASK.name,
    items_changed: [{ activity: ACTIVITY.name, activity_title: "Rilascio", item: 1, text: "Note", done: true }],
  }));
  mockApi({
    "GET /projects/acme/notes": [],
    "GET /projects/acme/today": { date: "2026-11-11", due_soon_days: 3, waiting: [], overdue: [], due_soon: [], to_close: [] },
    "GET /projects/acme/activities": [ACTIVITY],
    "GET /projects/acme/agent-tasks": () => tasks,
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/chatbots": [],
    "POST /projects/acme/activities/attivita-rilascio.md/items/2/agent-task": created,
    "PUT /projects/acme/agent-tasks/agent-task-note.md": saved,
  });
  return { created, saved };
}

const renderData = (route = "/projects/acme/data") =>
  renderPage(<Routes>{zoneRoutes()}</Routes>, { route });

describe("an item's agent task", () => {
  it("shows the task's status and opens it inside the activity", async () => {
    api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));

    const badge = await screen.findByRole("button", { name: "Task della voce 1" });
    await waitFor(() => expect(badge).toHaveTextContent("Da verificare"));
    fireEvent.click(badge);

    expect(await screen.findByRole("button", { name: "← Rilascio" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Attività/, selected: true })).toBeInTheDocument();
  });

  it("«🤖» creates a task of the chosen type from the item and opens it", async () => {
    const { created } = api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Crea un agent task dalla voce 2" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Analisi" }));

    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(await created.mock.results[0].value).toMatchObject({ type: "analysis" });
    expect(await screen.findByRole("tab", { name: /Tutti i task/, selected: true })).toBeInTheDocument();
  });

  it("«🤖» waits for the activity to be saved", async () => {
    api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));

    fireEvent.change((await screen.findAllByLabelText("Testo della voce"))[1], { target: { value: "Taggare" } });

    expect(screen.getByRole("button", { name: "Crea un agent task dalla voce 2" })).toBeDisabled();
  });

  it("confirming the task says which items got checked", async () => {
    const shown = vi.spyOn(notifications, "show");
    const { saved } = api();
    renderData(`/projects/acme/data?note=${NOTE_TASK.name}`);

    fireEvent.click(await screen.findByRole("button", { name: /Conferma/ }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ status: "done" });
    await waitFor(() => expect(shown).toHaveBeenCalledWith(expect.objectContaining({
      message: "Voce «Note» di «Rilascio» spuntata: il task è fatto.",
    })));
  });
});
