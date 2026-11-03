import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "./DataTab";

afterEach(() => vi.unstubAllGlobals());

const task = (name: string, title: string, status: string) => ({
  name, title, status, type: "development", objective: "", context: "", criteria: [], constraints: "", references: [],
});
const NOTE_TASK = task("agent-task-note-di-rilascio.md", "Note di rilascio", "refinement");
const TAG_TASK = task("agent-task-tag.md", "Tag", "todo");
const ACTIVITY = {
  name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", description: "La 2.0",
  items: [{ text: "Dipendenze", done: true, priority: null, due: null }, { text: "Note", done: true, priority: null, due: null }],
  agent_tasks: [NOTE_TASK.name], references: [],
};

function renderData(route = "/projects/acme/data") {
  renderPage(<Routes><Route path="/projects/:project/data" element={<DataTab />} /></Routes>, { route });
}

/** The fake API keeps what is saved: the activity and the agent tasks. */
function api() {
  let activity = ACTIVITY;
  let tasks = [NOTE_TASK, TAG_TASK];
  const savedActivity = vi.fn(async (request: Request) => { activity = { ...activity, ...(await request.json()) }; return activity; });
  const createdTask = vi.fn(async (request: Request) => {
    const created = { ...task("agent-task-nuovo.md", "", "created"), ...(await request.json()), name: "agent-task-nuovo.md" };
    tasks = [...tasks, created];
    return created;
  });
  mockApi({
    "GET /projects/acme/notes": [],
    "GET /projects/acme/activities": () => [activity],
    "PUT /projects/acme/activities/attivita-rilascio.md": savedActivity,
    "GET /projects/acme/agent-tasks": () => tasks,
    "POST /projects/acme/agent-tasks": createdTask,
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/chatbots": [],
  });
  return { savedActivity, createdTask };
}

describe("activities", () => {
  it("suggests «done» when every item is done", async () => {
    const { savedActivity } = api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));

    fireEvent.click(await screen.findByRole("button", { name: /Tutte le voci sono fatte: segna fatta/ }));

    await waitFor(() => expect(savedActivity).toHaveBeenCalled());
    expect(await savedActivity.mock.results[0].value).toMatchObject({ status: "done" });
    await waitFor(() => expect(screen.queryByRole("button", { name: /segna fatta/ })).not.toBeInTheDocument());
  });

  it("links agent tasks: shows them, creates one already linked, links and unlinks", async () => {
    const { savedActivity, createdTask } = api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));

    expect(await screen.findByRole("button", { name: "Note di rilascio" })).toBeInTheDocument();
    expect(screen.getByText("In rifinitura")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Nuovo agent task/ }));
    const dialog = await screen.findByRole("dialog", { name: "Nuovo agent task" });
    fireEvent.change(within(dialog).getByLabelText("Titolo"), { target: { value: "Changelog" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crea" }));

    await waitFor(() => expect(savedActivity).toHaveBeenCalledTimes(1)); // saved at once: the new task is not left alone
    expect(await createdTask.mock.results[0].value).toMatchObject({ title: "Changelog", status: "created" });
    expect(await savedActivity.mock.results[0].value).toMatchObject({ agent_tasks: [NOTE_TASK.name, "agent-task-nuovo.md"] });

    fireEvent.click(screen.getByPlaceholderText("Collega un agent task esistente…"));
    fireEvent.click(await screen.findByRole("option", { name: "Tag" }));
    fireEvent.click(screen.getByRole("button", { name: "Scollega Note di rilascio" }));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(savedActivity).toHaveBeenCalledTimes(2));
    expect(await savedActivity.mock.results[1].value).toMatchObject({ agent_tasks: ["agent-task-nuovo.md", TAG_TASK.name] });
  });

  it("an activity's task opens in the Agent task tab, which says where it is born from", async () => {
    api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Note di rilascio" }));

    expect(await screen.findByRole("tab", { name: /Agent task/, selected: true })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Note di rilascio")).toBeInTheDocument();
    expect(screen.getByText(/Nasce da/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Rilascio" }));

    expect(await screen.findByRole("tab", { name: /Attività/, selected: true })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("La 2.0")).toBeInTheDocument();
  });

  it("a task born from nothing says nothing", async () => {
    api();
    renderData("/projects/acme/data?note=agent-task-tag.md");

    expect(await screen.findByDisplayValue("Tag")).toBeInTheDocument();
    expect(screen.queryByText(/Nasce da/)).not.toBeInTheDocument();
  });
});
