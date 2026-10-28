import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "./DataTab";

afterEach(() => vi.unstubAllGlobals());

const TASK = {
  name: "agent-task-fix-porto.md", title: "Fix porto", status: "in_progress", objective: "Sbloccare il porto", context: "",
  criteria: [{ text: "test verdi", done: false }], constraints: "",
};
const TODO = {
  name: "todo-list-rilascio.md", title: "Rilascio",
  items: [{ text: "tag", done: true, priority: "high", due: "2026-11-02" }, { text: "note", done: false, priority: null, due: null }],
};
const NOTES = [
  { name: "agent-task-fix-porto.md", kind: "note", size: 1, modified_at: "2026-10-25T10:00:00Z", note_type: "agent_task" },
  { name: "decisioni.md", kind: "note", size: 1, modified_at: "2026-10-25T10:00:00Z", note_type: "generic" },
];

const renderData = () =>
  renderPage(<Routes><Route path="/projects/:project/data" element={<DataTab />} /></Routes>, { route: "/projects/acme/data" });

describe("typed notes", () => {
  it("the generic notes leave out the typed ones", async () => {
    mockApi({ "GET /projects/acme/notes": NOTES, "GET /projects/acme/notes/decisioni.md": { name: "decisioni.md", content: "# Decisioni" } });
    renderData();

    expect(await screen.findByDisplayValue("# Decisioni")).toBeInTheDocument();
    expect(screen.queryByText("agent-task-fix-porto.md")).not.toBeInTheDocument();
  });

  it("deleting an agent task can delete its Copilot sessions too", async () => {
    const order: string[] = [];
    const sessionsDeleted = vi.fn((request: Request) => {
      order.push(`sessioni ${new URL(request.url).searchParams.get("task_note")}`);
      return { deleted: 2 };
    });
    const noteDeleted = vi.fn(() => { order.push("nota"); return {}; });
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/copilot-sessions": [{ id: 1, task_note: TASK.name }, { id: 2, task_note: TASK.name }, { id: 3, task_note: "agent-task-altro.md" }],
      "DELETE /projects/acme/copilot-sessions": sessionsDeleted,
      "DELETE /projects/acme/notes/agent-task-fix-porto.md": noteDeleted,
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Elimina" }));
    expect(await screen.findByRole("checkbox", { name: /Elimina anche le 2 sessioni Copilot di questo task/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Sì, elimina" }));

    await waitFor(() => expect(noteDeleted).toHaveBeenCalled());
    expect(order).toEqual(["sessioni agent-task-fix-porto.md", "nota"]);
  });

  it("edits an agent task as a form and saves its fields", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: TASK.name, ...(await request.json()) }));
    mockApi({ "GET /projects/acme/notes": NOTES, "GET /projects/acme/agent-tasks": [TASK], "PUT /projects/acme/agent-tasks/agent-task-fix-porto.md": saved });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    expect(await screen.findByDisplayValue("Sbloccare il porto")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Fatto" }));
    fireEvent.click(screen.getByRole("button", { name: /Criterio/ }));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    const body = await saved.mock.results[0].value;
    expect(body.status).toBe("done");
    expect(body.criteria).toEqual([{ text: "test verdi", done: false }]); // the empty criterion is dropped
  });

  it("creates a todo list from its title and shows its progress", async () => {
    const created = vi.fn(async (request: Request) => ({ name: "todo-list-spesa.md", ...(await request.json()) }));
    mockApi({ "GET /projects/acme/notes": NOTES, "GET /projects/acme/todo-lists": [TODO], "POST /projects/acme/todo-lists": created });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Todo list/ }));
    expect(await screen.findByText("1/2")).toBeInTheDocument();
    expect(screen.getByDisplayValue("2026-11-02")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Nuova todo list/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Titolo"), { target: { value: "Spesa" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crea" }));

    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(await created.mock.results[0].value).toEqual({ name: "todo-list-spesa.md", title: "Spesa", items: [] });
  });
});
