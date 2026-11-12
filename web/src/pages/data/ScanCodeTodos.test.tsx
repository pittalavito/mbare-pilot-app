import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";

afterEach(() => vi.unstubAllGlobals());

const NOTE = "code-reference-todo-mbare-pilot.md";
const REFERENCE = {
  name: NOTE, title: "TODO Mbare Pilot", kind: "code_reference", source: "todoMbarePilot", source_url: "", repository: "", path: "", lines: "",
  content: "### api/login.py\n- riga 2: Rifattorizza", linked_from: [],
};
const TASK = { name: "agent-task-login.md", title: "Login", status: "todo", type: "development", objective: "", context: "",
  criteria: [], constraints: "", references: [] };

/** The scan finds the comments: the note appears in the references once it ran. */
function api(extra: Record<string, unknown> = {}) {
  let scanned = false;
  const scan = vi.fn(() => { scanned = true; return { note: NOTE, created: true, files: 1, comments: 1 }; });
  mockApi({
    "GET /projects/acme/notes": [],
    "GET /projects/acme/agent-tasks": [TASK],
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/chatbots": [],
    "GET /projects/acme/references": () => (scanned ? [REFERENCE] : []),
    "POST /projects/acme/code-todos": scan,
    ...extra,
  });
  return scan;
}

const renderData = (route = "/projects/acme/data") =>
  renderPage(<Routes>{zoneRoutes()}</Routes>, { route });

describe("Todo del codice", () => {
  it("in a task's references: scans and links the note to the task", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: TASK.name, ...(await request.json()) }));
    const scan = api({ "PUT /projects/acme/agent-tasks/agent-task-login.md": saved });
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));

    fireEvent.click(await screen.findByRole("button", { name: /Todo del codice/ }));

    expect(await screen.findByText("1 commento todoMbarePilot in 1 file: nota creata.")).toBeInTheDocument();
    expect(scan).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("TODO Mbare Pilot")).toBeInTheDocument(); // linked, to save with the task
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect((await saved.mock.results[0].value).references).toEqual([NOTE]);
  });

  it("in «Progetto» → Riferimenti: scans and opens the note", async () => {
    api({ "GET /projects/acme/data-settings": { visible_note_types: ["agent_task", "code_reference"] } });
    renderData("/projects/acme/project");
    fireEvent.click(await screen.findByRole("tab", { name: /Riferimenti/ }));

    fireEvent.click(await screen.findByRole("button", { name: /Todo del codice/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByDisplayValue(/riga 2: Rifattorizza/)).toBeInTheDocument();
  });

  it("says when nothing is found, and the errors", async () => {
    api({ "POST /projects/acme/code-todos": { note: null, created: false, files: 0, comments: 0 } });
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Todo del codice/ }));
    expect(await screen.findByText("Nessun commento todoMbarePilot nel codice: scrivilo così, // todoMbarePilot{descrizione}")).toBeInTheDocument();
    expect(screen.queryByText("TODO Mbare Pilot")).not.toBeInTheDocument();
  });

  it("says how many are written wrong", async () => {
    api({ "POST /projects/acme/code-todos": { note: NOTE, created: false, files: 1, comments: 1, malformed: 2 } });
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Todo del codice/ }));

    expect(await screen.findByText("1 commento todoMbarePilot in 1 file; 2 da correggere (scritti male, elencati nella nota): nota aggiornata."))
      .toBeInTheDocument();
  });

  it("explains how the comment is written, with a copy button", async () => {
    api();
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Come si scrive un commento todoMbarePilot" }));

    expect(await screen.findByText("Come si scrive il commento")).toBeInTheDocument();
    expect(screen.getByText(/esatto, maiuscole comprese/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copia il commento" })).toBeInTheDocument();
    expect(screen.getByText(/Rifattorizza il controllo della password/)).toBeInTheDocument();
  });

  it("shows the server's error", async () => {
    api({ "POST /projects/acme/code-todos": () => new Response(JSON.stringify({ detail: "Esiste già, scritto a mano" }), { status: 409 }) });
    renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Todo del codice/ }));

    expect(await screen.findByText(/scritto a mano/)).toBeInTheDocument();
  });
});
