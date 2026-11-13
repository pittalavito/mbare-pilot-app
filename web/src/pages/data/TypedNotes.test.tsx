import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";
import { sectionOfNote } from "../project/ProjectZone";
import { noteZone } from "../project/redirects";

afterEach(() => vi.unstubAllGlobals());

const TASK = {
  name: "agent-task-fix-porto.md", title: "Fix porto", status: "in_progress", objective: "Sbloccare il porto", context: "",
  criteria: [{ text: "test verdi", done: false }], constraints: "",
};
const TODO = {
  name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", description: "La 2.0", agent_tasks: [] as string[], references: [] as string[],
  items: [{ text: "tag", done: true, priority: "high", due: "2026-11-02" }, { text: "note", done: false, priority: null, due: null }],
};
const NOTES = [
  { name: "agent-task-fix-porto.md", kind: "note", size: 1, modified_at: "2026-10-25T10:00:00Z", note_type: "agent_task" },
  { name: "decisioni.md", kind: "note", size: 1, modified_at: "2026-10-25T10:00:00Z", note_type: "generic" },
];

const renderData = (route = "/projects/acme/data") =>
  renderPage(<Routes>{zoneRoutes()}</Routes>, { route });

describe("agent task status and type", () => {
  const task = (name: string, title: string, status: string, type: string, extra = {}) => ({
    name, title, status, type, objective: "", context: "", criteria: [], constraints: "", references: [], ...extra,
  });
  const TASKS = [
    task("agent-task-login.md", "Login", "refinement", "analysis"),
    task("agent-task-export.md", "Export", "todo", "development"),
    task("agent-task-vecchio.md", "Vecchio", "done", "development"),
  ];
  const BASE = { "GET /projects/acme/notes": NOTES, "GET /projects/acme/copilot-sessions": [], "GET /projects/acme/chatbots": [] };
  const item = (title: string) => screen.queryByText(title, { selector: ".mantine-NavLink-label" })?.closest(".mantine-NavLink-root") ?? null;
  const group = (label: string) => screen.getAllByRole("button").find((button) => button.hasAttribute("aria-expanded") && button.textContent?.includes(label));

  it("groups the tasks by status, the done ones closed, filters by type and creates in the filtered type", async () => {
    const created = vi.fn(async (request: Request) => ({ name: "agent-task-nuovo.md", ...(await request.json()) }));
    mockApi({ ...BASE, "GET /projects/acme/agent-tasks": TASKS, "POST /projects/acme/agent-tasks": created });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    await screen.findByText("Login", { selector: ".mantine-NavLink-label" });
    expect(group("Creati")).toHaveTextContent("Creati0");
    expect(group("In rifinitura")).toHaveTextContent("In rifinitura1");
    expect(group("Fatti")).toHaveAttribute("aria-expanded", "false");
    expect(item("Vecchio")).toBeNull(); // in the closed «Fatti»
    expect(within(item("Login") as HTMLElement).getByText("Analisi")).toBeInTheDocument();
    fireEvent.click(group("Fatti")!);
    expect(item("Vecchio")).not.toBeNull();

    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Filtra per tipo" })).getByRole("radio", { name: "Sviluppo" }));
    await waitFor(() => expect(item("Login")).toBeNull());
    expect(item("Export")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Nuovo task/ }));
    fireEvent.change(await screen.findByLabelText("Titolo", { selector: "[data-autofocus]" }), { target: { value: "Nuovo" } });
    fireEvent.click(screen.getByRole("button", { name: "Crea" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(await created.mock.results[0].value).toMatchObject({ title: "Nuovo", status: "created", type: "development" });
  });

  it("the path shows the one action of each status and saves a move at once", async () => {
    let current = TASKS[0];
    const saved = vi.fn(async (request: Request) => { current = { ...current, ...(await request.json()) }; return current; });
    mockApi({ ...BASE, "GET /projects/acme/agent-tasks": () => [current], "PUT /projects/acme/agent-tasks/agent-task-login.md": saved });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    expect(await screen.findByText("Manca ancora l'obiettivo e i criteri di accettazione.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delega a Copilot/ })).not.toBeInTheDocument(); // not ready
    fireEvent.change(screen.getByLabelText("Obiettivo", { exact: false }), { target: { value: "Capire il login" } });
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Tipo del task" })).getByRole("radio", { name: "Task Jira" }));
    fireEvent.click(screen.getByRole("button", { name: /Segna da fare/ }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ status: "todo", type: "jira", objective: "Capire il login" }); // the form too
    expect(await screen.findByRole("button", { name: /Delega a Copilot/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Segna da fare/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Cambia stato/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "In corso" }));
    expect(await screen.findByText(/Copilot ci sta lavorando/)).toBeInTheDocument();
    expect(screen.getByText(/la sua chat è nel pannello dell'agente/)).toBeInTheDocument(); // no Copilot tab any more
    expect(screen.getByText(/«Salva come nota»/)).toBeInTheDocument(); // a Jira task: Copilot's answer becomes a note
    expect(within(screen.getByLabelText("Stato del task")).queryByText("Da verificare")).not.toBeInTheDocument(); // not in a plan-only task's path
  });

  it("«Rifinisci con il Refiner» moves a created task to refinement at once", async () => {
    let current = task("agent-task-grezzo.md", "Grezzo", "created", "development");
    const saved = vi.fn(async (request: Request) => { current = { ...current, ...(await request.json()) }; return current; });
    mockApi({ ...BASE, "GET /projects/acme/agent-tasks": () => [current], "PUT /projects/acme/agent-tasks/agent-task-grezzo.md": saved });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Rifinisci con il Refiner/ }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ status: "refinement" });
  });

  it("a development to verify is confirmed, or sent back to Copilot in its latest session", async () => {
    let current = task("agent-task-export.md", "Export", "to_verify", "development", { objective: "x", criteria: [{ text: "ok", done: false }] });
    const saved = vi.fn(async (request: Request) => { current = { ...current, ...(await request.json()) }; return current; });
    const sentBack = vi.fn(async (request: Request) => ({ id: 7, status: "queued", text: (await request.json()).text }));
    mockApi({
      ...BASE,
      "GET /projects/acme/copilot-sessions": [{ id: 7, task_note: "agent-task-export.md", status: "done" }, { id: 3, task_note: "agent-task-export.md", status: "done" }],
      "GET /projects/acme/agent-tasks": () => [current],
      "PUT /projects/acme/agent-tasks/agent-task-export.md": saved,
      "POST /copilot-sessions/7/send-back": sentBack,
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    expect(await screen.findByText(/commit e push li fai tu/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Rimanda a Copilot/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Rimanda" })).toBeDisabled(); // nothing written yet
    fireEvent.change(within(dialog).getByLabelText("Cosa deve sistemare"), { target: { value: "Aggiungi un test" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Rimanda" }));
    await waitFor(() => expect(sentBack).toHaveBeenCalled());
    expect(await sentBack.mock.results[0].value).toMatchObject({ text: "Aggiungi un test" }); // the newest session

    fireEvent.click(screen.getByRole("button", { name: /Conferma/ }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ status: "done" });
  });

  it("sending back without a Copilot session says to delegate again", async () => {
    mockApi({ ...BASE, "GET /projects/acme/agent-tasks": [task("agent-task-export.md", "Export", "to_verify", "development")] });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Rimanda a Copilot/ }));
    expect(await screen.findByText(/Nessuna sessione Copilot per questo task/)).toBeInTheDocument();
  });
});

describe("typed notes", () => {
  it("the generic notes leave out the typed ones", async () => {
    mockApi({
      "GET /projects/acme/notes": NOTES, "GET /projects/acme/notes/decisioni.md": { name: "decisioni.md", content: "# Decisioni" },
      "GET /projects/acme/wip": { content: "", pending_words: 0 },
    });
    renderData("/projects/acme/project?tab=notes"); // the generic notes are in «Progetto»

    fireEvent.click(await screen.findByText("decisioni.md"));
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

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Elimina" }));
    expect(await screen.findByRole("checkbox", { name: /Elimina anche le 2 sessioni Copilot di questo task/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Sì, elimina" }));

    await waitFor(() => expect(noteDeleted).toHaveBeenCalled());
    expect(order).toEqual(["sessioni agent-task-fix-porto.md", "nota"]);
  });

  it("links references to an agent task: a new one, an existing one, and unlinks", async () => {
    const REFERENCE = (name: string, title: string, kind: string, extra = {}) => ({
      name, title, kind, source: "", source_url: "", repository: "", path: "", lines: "", content: "", linked_from: [], ...extra,
    });
    const created = vi.fn(async (request: Request) => REFERENCE("code-reference-login.md", "Login", "code_reference", await request.json()));
    const saved = vi.fn(async (request: Request) => ({ name: TASK.name, ...(await request.json()) }));
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/agent-tasks": [{ ...TASK, references: ["context-reference-procedura.md"] }],
      "GET /projects/acme/references": [
        REFERENCE("context-reference-procedura.md", "Procedura", "context_reference", { source: "confluence", linked_from: [TASK.name] }),
        REFERENCE("context-reference-porto.md", "Porto", "context_reference"),
      ],
      "POST /projects/acme/references": created,
      "PUT /projects/acme/agent-tasks/agent-task-fix-porto.md": saved,
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    expect(await screen.findByText("Procedura")).toBeInTheDocument();
    expect(screen.getByText("confluence")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Nuovo riferimento/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText("Codice"));
    fireEvent.change(within(dialog).getByLabelText("Titolo"), { target: { value: "Login" } });
    fireEvent.change(within(dialog).getByLabelText("File"), { target: { value: "src/auth/login.py" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crea e collega" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(await created.mock.results[0].value).toMatchObject({ kind: "code_reference", title: "Login", path: "src/auth/login.py" });

    fireEvent.click(await screen.findByRole("button", { name: "Scollega Procedura" }));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ references: ["code-reference-login.md"] });
  });

  it("edits an agent task as a form and saves its fields", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: TASK.name, ...(await request.json()) }));
    mockApi({ "GET /projects/acme/notes": NOTES, "GET /projects/acme/agent-tasks": [TASK], "PUT /projects/acme/agent-tasks/agent-task-fix-porto.md": saved });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    expect(await screen.findByDisplayValue("Sbloccare il porto")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Criterio/ }));
    fireEvent.click(screen.getByRole("button", { name: /Cambia stato/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Fatto" })); // saved at once, with the form

    await waitFor(() => expect(saved).toHaveBeenCalled());
    const body = await saved.mock.results[0].value;
    expect(body.status).toBe("done");
    expect(body.criteria).toEqual([{ text: "test verdi", done: false }]); // the empty criterion is dropped
  });

  it("creates an activity from its title and shows status and progress", async () => {
    const created = vi.fn(async (request: Request) => ({ name: "attivita-spesa.md", ...(await request.json()) }));
    mockApi({ "GET /projects/acme/notes": NOTES, "GET /projects/acme/activities": [TODO], "POST /projects/acme/activities": created,
      "GET /projects/acme/agent-tasks": [] });
    renderData();

    expect(await screen.findByRole("tab", { name: /Attività/, selected: true })).toBeInTheDocument(); // «Lavoro» opens on the activities
    expect(await screen.findByText("1/2")).toBeInTheDocument();
    expect(screen.getByDisplayValue("La 2.0")).toBeInTheDocument();
    expect(screen.getByDisplayValue("2026-11-02")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Nuova attività/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Titolo"), { target: { value: "Spesa" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crea" }));

    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(await created.mock.results[0].value).toEqual({
      name: "attivita-spesa.md", title: "Spesa", status: "todo", description: "", items: [], agent_tasks: [], references: [], learned: "",
    });
  });

  it("the settings choose what «Progetto» shows: references get their own section; activities and tasks stay in «Lavoro»", async () => {
    const saved = vi.fn(async (request: Request) => request.json());
    mockApi({
      "GET /projects/acme/data-settings": { visible_note_types: ["generic", "agent_task", "activity"] },
      "PUT /projects/acme/data-settings": saved,
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/references": [{
        name: "context-reference-orfano.md", title: "Orfano", kind: "context_reference", source: "", source_url: "", repository: "", path: "",
        lines: "", content: "", linked_from: [],
      }],
    });
    renderData("/projects/acme/settings"); // the old tab: «Progetto» → Impostazioni

    expect(await screen.findByRole("tab", { name: /Impostazioni/, selected: true })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Riferimenti/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Attività/ })).not.toBeInTheDocument(); // not a choice any more
    fireEvent.click(await screen.findByRole("checkbox", { name: /Riferimenti di contesto/ }));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toEqual({
      visible_note_types: ["generic", "agent_task", "activity", "context_reference"], files_visible: true, due_soon_days: 3,
    });
    fireEvent.click(await screen.findByRole("tab", { name: /Riferimenti/ }));
    expect(await screen.findByText("Non collegato a niente")).toBeInTheDocument();
  });
});

describe("links to a note", () => {
  it("open the note's tab with the note open", async () => {
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/agent-tasks": [{ ...TASK, type: "development", references: [] }, { ...TASK, name: "agent-task-altro.md", title: "Altro", type: "analysis", references: [] }],
      "GET /projects/acme/copilot-sessions": [],
      "GET /projects/acme/chatbots": [],
      "GET /projects/acme/activities": [], // born from no activity: it opens in «Tutti i task»
    });
    renderPage(<Routes>{zoneRoutes()}</Routes>, { route: "/projects/acme/data?note=agent-task-altro.md" });

    expect(await screen.findByRole("tab", { name: /Tutti i task/, selected: true })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Altro")).toBeInTheDocument(); // the linked task, not the first one
  });

  it("know which zone and section each note is in", () => {
    const notes = [null, "agent-task-a.md", "attivita-b.md", "wip.md", "code-reference-c.md", "context-reference-d.md", "appunti.md"];
    expect(notes.map(noteZone)).toEqual(["work", "work", "work", "work", "project", "project", "project"]);
    expect(notes.map(sectionOfNote)).toEqual([null, null, null, null, "references", "references", "notes"]); // «Lavoro» ones: none
  });
});
