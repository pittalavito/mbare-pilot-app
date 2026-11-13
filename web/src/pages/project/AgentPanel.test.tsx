import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AutomationCacheEntry, Chatbot, Message } from "../../api/chat";
import type { CopilotSession } from "../../api/copilot";
import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";
import { noteOfLink } from "./AgentPanel";

/** Plan 13b: the agent panel at the right of «Lavoro» and «Automation», with
 * the agent of what is open (Segretario, Refiner, Copilot, Architetto), what was
 * the Chat tab (conversations, details, cache controls) and the Copilot tab. */

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => { try { window.localStorage.clear(); } catch { /* no storage */ } });

const bot = (id: number, name: string, kind: Chatbot["kind"], extra: Partial<Chatbot> = {}): Chatbot => ({
  id, project_name: "acme", name, kind, description: "", system_prompt: `Sono ${name}.`, prompt_version: 1, model: "mock/echo", max_steps: 4,
  tool_names: [], automation_cache: false, ...extra,
});
const SECRETARY = bot(8, "Segretario", "secretary");
const REFINER = bot(7, "Refiner", "refiner");
const ARCHITECT = bot(9, "Architetto", "automation");
const CUSTOM = bot(10, "Assistente Jira", "custom");
const task = (name: string, title: string, status: string, extra = {}) => ({
  name, title, status, type: "development", objective: "", context: "", criteria: [], constraints: "", references: [], tests: null, ...extra,
});
const CREATED = task("agent-task-login.md", "Login", "created");
const DELEGATED = task("agent-task-fix.md", "Fix porto", "in_progress");
const ACTIVITY = {
  name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", description: "La 2.0", learned: "", references: [],
  items: [], agent_tasks: [CREATED.name],
};
const message = (id: number, role: string, content: string, conversation = 3): Message => ({
  id, conversation_id: conversation, role, content, run_id: null, created_at: "2026-11-13T10:00:00Z",
});
const session = (patch: Partial<CopilotSession> = {}): CopilotSession => ({
  id: 4, project_name: "acme", task_note: DELEGATED.name, repository: "api", prompt: "", model: "", status: "planning", cancel_requested: false,
  head_before: null, head_after: null, head_moved: false, changed_files: [], premium_requests: 1, error: null,
  created_at: "2026-11-13T10:00:00Z", updated_at: "2026-11-13T10:00:00Z", started_at: null, finished_at: null, ...patch,
});
const COPILOT_MESSAGES = [
  { id: 1, role: "user", content: "Ti affido il task…", created_at: "2026-11-13T10:00:00Z" },
  { id: 2, role: "copilot", content: "**Domanda**: ValueError o ZeroDivisionError?", created_at: "2026-11-13T10:00:10Z" },
];
const TURNS = {
  total: { premium_requests: 2, ai_credits: 0.68, input_tokens: 53472, output_tokens: 194, cache_read_tokens: 0, cache_write_tokens: 0, reasoning_tokens: 0,
           api_duration_ms: 0 },
  turns: [],
};

function Where() {
  const location = useLocation();
  return <div data-testid="where">{location.pathname + location.search}</div>;
}

/** The project page; ``conversations`` per chatbot id (the panel filters by context in the API: here what it gets). */
function api(extra: Record<string, unknown> = {}) {
  const bodies: unknown[] = [];
  const created: unknown[] = [];
  mockApi({
    ...PROJECT_API,
    "GET /projects/acme/chatbots": [SECRETARY, REFINER, ARCHITECT, CUSTOM],
    "GET /projects/acme/activities": [ACTIVITY],
    "GET /projects/acme/agent-tasks": [CREATED, DELEGATED],
    "GET /projects/acme/copilot-sessions": [session()],
    "GET /chatbots/8/conversations": [], "GET /chatbots/7/conversations": [], "GET /chatbots/9/conversations": [], "GET /chatbots/10/conversations": [],
    "GET /chatbots/8/automation-cache": [], "GET /chatbots/7/automation-cache": [],
    "POST /chatbots/8/conversations": async (request: Request) => { created.push(await request.json()); return { id: 3, chatbot_id: 8, title: "", context: "" }; },
    "POST /chatbots/7/conversations": async (request: Request) => { created.push(await request.json()); return { id: 3, chatbot_id: 7, title: "", context: "" }; },
    "POST /conversations/3/messages": async (request: Request) => { bodies.push(await request.json()); return {}; },
    "GET /conversations/3/messages": [],
    "GET /copilot/status": { installed: true, version: "x", prompts: [], default_model: "", models: [] },
    "GET /copilot-sessions/4/messages": COPILOT_MESSAGES,
    "GET /copilot-sessions/4/turns": TURNS,
    "GET /functions": [], "GET /models/choices": { choices: ["mock/echo"], usable: ["mock/echo"] }, "GET /tools": [], "GET /agents": [],
    ...extra,
  });
  return { bodies, created };
}

const renderAt = (route: string) =>
  renderPage(<><Routes>{projectRoutes()}</Routes><Routes><Route path="*" element={<Where />} /></Routes></>, { route, path: "/*" });

const panel = async () => within(await screen.findByTestId("agent-panel"));
const agent = async () => (await panel()).getByRole("textbox", { name: "Agente" });

describe("the agent of what is open", () => {
  it("an activity: the Segretario, its conversation about the activity and the activity sent with every message", async () => {
    const { bodies, created } = api();
    renderAt(`/projects/acme/work?note=${ACTIVITY.name}`);

    expect(await agent()).toHaveValue("Segretario");
    expect((await panel()).getByText("Hai aperto un'attività")).toBeInTheDocument();
    const box = (await panel()).getByPlaceholderText(/Scrivi a Segretario/);
    fireEvent.change(box, { target: { value: "aggiungi una voce" } });
    fireEvent.keyDown(box, { key: "Enter" });

    await waitFor(() => expect(bodies).toEqual([{ text: "aggiungi una voce", open_note: ACTIVITY.name }]));
    expect(created).toEqual([{ context: ACTIVITY.name }]);
  });

  it("a task to refine: the Refiner; «Rifinisci con il Refiner» puts the request in its box, not sent", async () => {
    const { bodies } = api();
    renderAt(`/projects/acme/work?note=${CREATED.name}`);

    expect(await agent()).toHaveValue("Refiner");
    fireEvent.click(await screen.findByRole("button", { name: /Rifinisci con il Refiner/ }));
    expect((await panel()).getByPlaceholderText(/Scrivi a Refiner/)).toHaveValue("Rifinisci questo task.");
    expect(bodies).toEqual([]);
  });

  it("a delegated task: Copilot's chat, answered, with the ok", async () => {
    const sent = vi.fn(async (request: Request) => ({ ...session(), ...(await request.json()) }));
    const approved = vi.fn(() => session({ status: "queued" }));
    api({ "POST /copilot-sessions/4/messages": sent, "POST /copilot-sessions/4/approve": approved });
    renderAt(`/projects/acme/work?note=${DELEGATED.name}`);

    expect(await agent()).toHaveValue("Copilot");
    expect(await screen.findByText("Domanda")).toHaveProperty("tagName", "STRONG");
    expect(await screen.findByText(/0,68 crediti AI · 2 richieste premium/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Rispondi a Copilot/), { target: { value: "ValueError" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/Rispondi a Copilot/), { key: "Enter" });
    await waitFor(() => expect(sent).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /Ok, parti/ }));
    await waitFor(() => expect(approved).toHaveBeenCalled());
  });

  it("a plan-only delegated task: Copilot's answer is saved as a note, no ok", async () => {
    const saved = vi.fn(() => ({ note: "analisi-fix.md", session: session() }));
    api({ "GET /projects/acme/agent-tasks": [CREATED, { ...DELEGATED, type: "analysis" }], "POST /copilot-sessions/4/save-note": saved });
    renderAt(`/projects/acme/work?note=${DELEGATED.name}`);

    const save = await screen.findByRole("button", { name: /Salva come nota/ });
    await waitFor(() => expect(save).toBeEnabled());
    expect(screen.queryByRole("button", { name: /Ok, parti/ })).not.toBeInTheDocument();
    fireEvent.click(save);
    await waitFor(() => expect(saved).toHaveBeenCalled());
  });

  it("the zone Automation: the Architetto", async () => {
    api();
    renderAt("/projects/acme/automation");
    expect(await agent()).toHaveValue("Architetto");
  });

  it("a hand-picked agent lasts until what is open changes", async () => {
    api();
    renderAt(`/projects/acme/work?note=${ACTIVITY.name}`);

    fireEvent.click(await agent());
    fireEvent.click(await screen.findByRole("option", { name: "Assistente Jira (personalizzato)" }));
    expect(await agent()).toHaveValue("Assistente Jira (personalizzato)");
    expect((await panel()).getByText(/Scelto a mano/)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("tab", { name: /Tutti i task/ }));
    await waitFor(async () => expect(await agent()).not.toHaveValue("Assistente Jira (personalizzato)"));
  });
});

describe("the panel", () => {
  it("hides, remembered; «Progetto» has none", async () => {
    api();
    renderAt("/projects/acme/work");
    expect(await screen.findByTestId("agent-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Nascondi l'agente" }));
    expect(screen.queryByTestId("agent-panel")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("mbare-pilot.agent-panel-hidden")).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: /Mostra l'agente/ }));
    expect(await screen.findByTestId("agent-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "🗂️ Progetto" }));
    await waitFor(() => expect(screen.queryByTestId("agent-panel")).not.toBeInTheDocument());
  });

  it("reopens the latest conversation of the context, with the others in a menu", async () => {
    const conversation = (id: number, title: string) => ({ id, chatbot_id: 8, title, context: ACTIVITY.name, created_at: "", updated_at: "" });
    api({
      "GET /chatbots/8/conversations": [conversation(3, "Voci nuove"), conversation(5, "Scadenze")],
      "GET /conversations/3/messages": [message(1, "user", "aggiungi una voce"), message(2, "assistant", "**Fatto**")],
    });
    renderAt(`/projects/acme/work?note=${ACTIVITY.name}`);

    expect(await screen.findByText("Fatto")).toHaveProperty("tagName", "STRONG");
    expect((await panel()).getByRole("textbox", { name: "Conversazione" })).toHaveValue("Voci nuove");
    fireEvent.click((await panel()).getByRole("button", { name: /Nuova/ }));
    expect(await (await panel()).findByText(/Scrivi per iniziare/)).toBeInTheDocument();
  });

  it("a reference in an answer opens here; one that is gone says so", async () => {
    const NOTE = "code-reference-todo-mbare-pilot.md";
    const reference = { name: NOTE, title: "TODO Mbare Pilot", kind: "code_reference", source: "todoMbarePilot", source_url: "", repository: "",
      path: "", lines: "", content: "### api/login.py\n- riga 2: Rifattorizza", linked_from: [] };
    const answer = [message(1, "user", "raccogli i todo"), message(2, "assistant", `Fatto: [TODO Mbare Pilot](/projects/acme/data?note=${NOTE}).`)];
    const conversations = [{ id: 3, chatbot_id: 7, title: "Todo", context: CREATED.name, created_at: "", updated_at: "" }];
    api({ "GET /chatbots/7/conversations": conversations, "GET /conversations/3/messages": answer, "GET /projects/acme/references": [reference] });
    renderAt(`/projects/acme/work?note=${CREATED.name}`);

    fireEvent.click(await screen.findByRole("link", { name: "TODO Mbare Pilot" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByDisplayValue(/riga 2: Rifattorizza/)).toBeInTheDocument();
  });

  it("changes the agent's model from its details", async () => {
    let secretary = SECRETARY;
    const patched = vi.fn(async (request: Request) => { secretary = { ...secretary, model: (await request.json()).model }; return secretary; });
    api({
      "GET /projects/acme/chatbots": () => [secretary, REFINER],
      "GET /models/choices": { choices: ["mock/echo", "openai/gpt-4o", "ollama/gemma3:4b"], usable: ["mock/echo", "openai/gpt-4o"] },
      "PATCH /chatbots/8/model": patched,
    });
    renderAt(`/projects/acme/work?note=${ACTIVITY.name}`);

    fireEvent.click((await panel()).getByRole("button", { name: /Dettagli/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Sono Segretario.")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("textbox", { name: "Modello" }));
    fireEvent.click(await screen.findByRole("option", { name: "ollama/gemma3:4b" }));
    expect(await screen.findByText("Manca la chiave del provider")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("textbox", { name: "Modello" }));
    fireEvent.click(await screen.findByRole("option", { name: "openai/gpt-4o" }));
    const save = within(dialog).getByRole("button", { name: "Salva" });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(patched).toHaveBeenCalled());
    expect(await patched.mock.results[0].value).toMatchObject({ model: "openai/gpt-4o" });
  });

  it("a chatbot with the automation cache shows its controls (kept in the code, no kind uses it today)", async () => {
    const entry: AutomationCacheEntry = {
      id: 1, chatbot_id: 8, message_id: 11, text: "com'è il repo?", pipeline_id: 7, pipeline_input: "main", hits: 3, created_at: "2026-11-13T10:00:00Z",
    };
    const pipeline = { id: 7, project_name: "acme", name: "Git status", description: "", active: true, steps: [{ name: "S", kind: "function", params: {} }], edges: [] };
    api({
      "GET /projects/acme/chatbots": [{ ...SECRETARY, automation_cache: true }, REFINER],
      "GET /chatbots/8/conversations": [{ id: 3, chatbot_id: 8, title: "Repo", context: "", created_at: "", updated_at: "" }],
      "GET /chatbots/8/automation-cache": [entry],
      "GET /projects/acme/pipelines": [pipeline],
      "GET /conversations/3/messages": [message(10, "user", "ciao"), message(12, "assistant", "Ciao"), message(11, "user", "com'è il repo?"),
                                        message(13, "assistant", "⚡ Git status avviata")],
    });
    renderAt("/projects/acme/work?note=wip.md");

    expect(await screen.findByText(/In cache →/)).toHaveTextContent("In cache → Git status · input «main» · usata 3 volte");
    expect(screen.getAllByRole("button", { name: /Metti in cache/ })).toHaveLength(1);
  });
});

describe("the links of the Chat and Copilot tabs", () => {
  it.each([
    ["/projects/acme/chat", "/projects/acme/work"],
    ["/projects/acme/copilot?session=4", `/projects/acme/work?note=${DELEGATED.name}`],
    ["/projects/acme/copilot?session=99", "/projects/acme/work"],
  ])("%s → %s", async (from, to) => {
    api();
    renderAt(from);
    await waitFor(() => expect(screen.getByTestId("where").textContent).toContain(to));
  });

  it("reads the note of an app link only", () => {
    const NOTE = "code-reference-x.md";
    expect(noteOfLink(`/projects/acme/data?note=${NOTE}`)).toBe(NOTE);
    expect(noteOfLink(`/projects/acme/project?note=${NOTE}`)).toBe(NOTE);
    expect(noteOfLink("/projects/acme/copilot?session=1")).toBeNull();
    expect(noteOfLink(`https://altro.it/projects/acme/data?note=${NOTE}`)).toBeNull();
  });
});
