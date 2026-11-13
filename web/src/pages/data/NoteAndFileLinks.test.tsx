import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";

afterEach(() => vi.unstubAllGlobals());

const TASK = { name: "agent-task-fix.md", title: "Fix", status: "todo", type: "development", objective: "", context: "", criteria: [],
  constraints: "", references: ["decisioni.md", "files/specifiche.pdf", "files/sparito.csv"] };
const NOTES = [
  { name: "decisioni.md", kind: "note", size: 10, modified_at: "2026-11-03T10:00:00Z", note_type: "generic" },
  { name: "appunti.md", kind: "note", size: 10, modified_at: "2026-11-03T10:00:00Z", note_type: "generic" },
  { name: "agent-task-fix.md", kind: "note", size: 10, modified_at: "2026-11-03T10:00:00Z", note_type: "agent_task" },
];
const FILES = [
  { name: "specifiche.pdf", kind: "file", size: 1258291, modified_at: "2026-11-03T10:00:00Z", note_type: null },
  { name: "dati.csv", kind: "file", size: 2048, modified_at: "2026-11-03T10:00:00Z", note_type: null },
];

const renderData = (route = "/projects/acme/data") =>
  renderPage(<Routes>{zoneRoutes()}</Routes>, { route });

describe("notes and files as references", () => {
  it("shows the linked note and file, links more of them and saves the links", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: TASK.name, ...(await request.json()) }));
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/files": FILES,
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/references": [],
      "GET /projects/acme/copilot-sessions": [],
      "GET /projects/acme/chatbots": [],
      "PUT /projects/acme/agent-tasks/agent-task-fix.md": saved,
    });
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));

    expect(await screen.findByText("specifiche.pdf")).toBeInTheDocument();
    expect(screen.getByText("1 MB")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Scarica" })).toHaveAttribute("href", expect.stringContaining("/api/projects/acme/files/specifiche.pdf"));
    expect(screen.getAllByText("decisioni.md").length).toBeGreaterThan(0);
    expect(screen.getByText("files/sparito.csv").parentElement).toHaveTextContent("non trovato"); // deleted by hand

    fireEvent.click(screen.getByPlaceholderText("Collega un riferimento, una nota o un file…"));
    expect(await screen.findByRole("option", { name: "appunti.md" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "agent-task-fix.md" })).not.toBeInTheDocument(); // only generic notes
    fireEvent.click(screen.getByRole("option", { name: "dati.csv" }));
    fireEvent.click(screen.getByRole("button", { name: "Scollega decisioni.md" }));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect((await saved.mock.results[0].value).references).toEqual(["files/specifiche.pdf", "files/sparito.csv", "files/dati.csv"]);
  });

  it("a linked note opens in «Progetto» → Note", async () => {
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/notes/decisioni.md": { name: "decisioni.md", content: "# Decisioni prese" },
      "GET /projects/acme/files": FILES,
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/references": [],
      "GET /projects/acme/copilot-sessions": [],
      "GET /projects/acme/chatbots": [],
    });
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Apri" }));

    expect(await screen.findByRole("tab", { name: /Note/, selected: true })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("# Decisioni prese")).toBeInTheDocument();
  });

  it("the settings hide the Files tab", async () => {
    let settings = { visible_note_types: ["generic", "agent_task"], files_visible: true };
    const saved = vi.fn(async (request: Request) => { settings = await request.json(); return settings; });
    mockApi({
      "GET /projects/acme/data-settings": () => settings,
      "PUT /projects/acme/data-settings": saved,
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/files": FILES,
    });
    renderData("/projects/acme/project");
    expect(await screen.findByRole("tab", { name: /File/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Impostazioni/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /📎 File/ }));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toEqual({ visible_note_types: ["generic", "agent_task"], files_visible: false, due_soon_days: 3 });
    await waitFor(() => expect(screen.queryByRole("tab", { name: /^📎 File$/ })).not.toBeInTheDocument());
    expect(within(screen.getByRole("tablist")).getByRole("tab", { name: /Impostazioni/ })).toBeInTheDocument();
  });
});
