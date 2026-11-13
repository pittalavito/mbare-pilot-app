import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Chatbot, Message } from "../../api/chat";
import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";
import { AutomationTab } from "../automation/AutomationTab";

/** Plan 11, from an agent to an automation: the Operator in the panel (its
 * commands waiting for an ok, «✅ Giusto: fanne un'automation»), the choice of
 * how to prepare in the delegation and the automations with fields. */

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => { try { window.localStorage.clear(); } catch { /* no storage */ } });

const OPERATOR: Chatbot = {
  id: 12, project_name: "acme", name: "Operatore Java", kind: "operator", description: "", system_prompt: "x", prompt_version: 1, model: "mock/echo",
  max_steps: 12, tool_names: ["run_command"], automation_cache: false,
};
const REFINER: Chatbot = { ...OPERATOR, id: 7, name: "Refiner", kind: "refiner", tool_names: [] };
const TASK = {
  name: "agent-task-login.md", title: "Login", status: "todo", type: "development", objective: "o", context: "", criteria: [], constraints: "",
  references: [], tests: null,
};
const step = (name: string, tool: string, params: Record<string, unknown>) => ({
  name, kind: "tool", input_template: "{input}", agent: null, agent_config_name: null, function_name: null, tool_name: tool, params,
  position_x: 0, position_y: 0,
});
const LEARNED = {
  id: 21, project_name: "acme", name: "Prepara feature", description: "", active: true, fields: ["branch", "base", "task", "repository", "altro"],
  purpose: "prepare", steps: [step("1. git_create_branch", "git_create_branch", { repository: "api", name: "{in:branch}", start_point: "{in:base}" })],
  edges: [{ source: "input", target: "1. git_create_branch", condition: "always", value: "" }],
};
const DEV = { test_scope: "all", prepare_automation: true, verify_automation: false, repositories: [], allowed_commands: [], suggested_commands: [],
              operator_chatbot_id: null };
const answer = (id: number, content: string, runId: string | null): Message => ({
  id, conversation_id: 3, role: "assistant", content, run_id: runId, created_at: "2026-11-13T10:00:00Z",
});

function api(extra: Record<string, unknown> = {}) {
  mockApi({
    ...PROJECT_API,
    "GET /projects/acme/chatbots": [REFINER, OPERATOR],
    "GET /projects/acme/agent-tasks": [TASK],
    "GET /projects/acme/dev-settings": DEV,
    "GET /projects/acme/pipelines": [LEARNED],
    "GET /projects/acme/command-requests": [],
    "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }],
    "GET /projects/acme/git/branches": { current: "develop", local: ["develop"], remote: [] },
    "GET /copilot/status": { installed: true, version: "x", prompts: [], default_model: "", models: [] },
    "GET /chatbots/7/conversations": [],
    "GET /chatbots/12/conversations": [{ id: 3, chatbot_id: 12, title: "Prepara", context: TASK.name, created_at: "2026-11-13T10:00:00Z" }],
    "GET /conversations/3/messages": [],
    ...extra,
  });
}

const renderTask = () => renderPage(<Routes>{projectRoutes()}</Routes>, { route: `/projects/acme/work?note=${TASK.name}` });

async function delegateWindow() {
  renderTask();
  fireEvent.click(await screen.findByRole("button", { name: /Delega a Copilot/ }));
  return screen.findByRole("dialog");
}

describe("the delegation's preparation", () => {
  it("runs a learned automation with its fields filled from the task", async () => {
    const started = vi.fn(async (request: Request) => ({ ...(await request.json()), id: 9 }));
    api({ "POST /projects/acme/copilot-sessions": started });
    const dialog = await delegateWindow();

    fireEvent.click(await within(dialog).findByDisplayValue("🧰 Prepara sviluppo"));
    fireEvent.click(await screen.findByRole("option", { name: /Prepara feature \(imparata\)/ }));
    expect(await within(dialog).findByDisplayValue("feature/login")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByLabelText("base")).toHaveValue("develop"));
    fireEvent.change(within(dialog).getByLabelText("altro"), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    await waitFor(() => expect(started).toHaveBeenCalled());
    expect(await started.mock.results[0].value).toMatchObject({
      prepare: [], learned: { automation_id: 21, fields: { branch: "feature/login", base: "develop", task: TASK.name, repository: "api", altro: "x" } },
    });
    expect(window.localStorage.getItem("mbare-pilot.prepare.acme")).toBe("learned:21"); // the default next time
  });

  it("when the learned automation fails it offers the Operator, with the error", async () => {
    window.localStorage.setItem("mbare-pilot.prepare.acme", "learned:21");
    api({ "POST /projects/acme/copilot-sessions": () => new Response(JSON.stringify({ detail: "Preparazione non riuscita: il branch c'è già" }), { status: 409 }) });
    const dialog = await delegateWindow();
    expect(await within(dialog).findByDisplayValue("🛠 Prepara feature (imparata)")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    fireEvent.click(await within(dialog).findByRole("button", { name: /Fallo fare all'Operatore/ }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Agente" })).toHaveValue("Operatore Java"));
    const box = screen.getByPlaceholderText(/Scrivi a Operatore Java/) as HTMLTextAreaElement;
    expect(box.value).toContain("feature/login");
    expect(box.value).toContain("il branch c'è già");
  });

  it("«Fallo fare all'Operatore» opens the panel's Operator with the request ready", async () => {
    api();
    const dialog = await delegateWindow();
    fireEvent.click(await within(dialog).findByDisplayValue("🧰 Prepara sviluppo"));
    fireEvent.click(await screen.findByRole("option", { name: /Fallo fare all'Operatore/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Chiedi all'Operatore" }));

    await waitFor(() => expect(screen.getByRole("textbox", { name: "Agente" })).toHaveValue("Operatore Java"));
    expect((screen.getByPlaceholderText(/Scrivi a Operatore Java/) as HTMLTextAreaElement).value)
      .toBe("Prepara api per il task agent-task-login.md: branch feature/login (crealo da develop se non c'è), aggiornato, poi il clean install.");
  });
});

describe("the Operator in the panel", () => {
  const pickOperator = async () => {
    fireEvent.click(await screen.findByRole("textbox", { name: "Agente" }));
    fireEvent.click(await screen.findByRole("option", { name: "Operatore Java" }));
  };

  it("asks for the commands outside the list: «Sempre» allows it and readies «continua»", async () => {
    const bodies: unknown[] = [];
    const answered = vi.fn(async (request: Request) => { bodies.push(await request.json()); return new Response(null, { status: 204 }); });
    const requests = [{ repository: "api", command: "mvn verify" }];
    api({ "GET /projects/acme/command-requests": () => requests, "POST /projects/acme/command-requests/answer": answered });
    renderTask();
    await pickOperator();

    expect(await screen.findByText("mvn verify")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sempre" }));
    await waitFor(() => expect(answered).toHaveBeenCalled());
    expect(bodies).toEqual([{ command: "mvn verify", allow: true, always: true }]);
    await waitFor(() => expect((screen.getByPlaceholderText(/Scrivi a Operatore Java/) as HTMLTextAreaElement).value).toBe("Ho permesso «mvn verify»: continua."));
  });

  it("«No» drops the request and nothing is readied", async () => {
    const bodies: unknown[] = [];
    api({
      "GET /projects/acme/command-requests": [{ repository: "", command: "rm -rf ." }],
      "POST /projects/acme/command-requests/answer": async (request: Request) => { bodies.push(await request.json()); return new Response(null, { status: 204 }); },
    });
    renderTask();
    await pickOperator();
    fireEvent.click(await screen.findByRole("button", { name: "No" }));
    await waitFor(() => expect(bodies).toEqual([{ command: "rm -rf .", allow: false, always: false }]));
    expect((screen.getByPlaceholderText(/Scrivi a Operatore Java/) as HTMLTextAreaElement).value).toBe("");
  });

  it("an answer that did things becomes an automation: steps kept, fields corrected, saved", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...LEARNED, id: 30, ...(await request.json()) }));
    api({
      "GET /conversations/3/messages": [answer(1, "Fatto: feature/login creato e build ok.", "run-1"), answer(2, "Ciao", null)],
      "GET /messages/1/learn-draft": {
        run_id: "run-1", cost_eur: 0.0021,
        steps: [{ tool: "git_status", args: { repository: "api" }, read_only: true },
                { tool: "git_create_branch", args: { repository: "api", name: "feature/login", start_point: "develop" }, read_only: false }],
        values: [{ value: "api", field: "" }, { value: "feature/login", field: "branch" }, { value: "develop", field: "base" }],
      },
      "POST /projects/acme/pipelines/learned": saved,
    });
    renderTask();
    await pickOperator();

    expect(await screen.findAllByRole("button", { name: /Giusto: fanne un'automation/ })).toHaveLength(1); // only the answer with a run
    fireEvent.click(screen.getByRole("button", { name: /Giusto: fanne un'automation/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/0,0021/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Tieni git_status")).not.toBeChecked();
    fireEvent.change(within(dialog).getByLabelText("Campo di api"), { target: { value: "Repository" } });
    fireEvent.change(within(dialog).getByLabelText("Nome"), { target: { value: "Prepara login" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({
      name: "Prepara login", purpose: "prepare", steps: [{ tool: "git_create_branch" }],
      fields: { api: "repository", "feature/login": "branch", develop: "base" },
    });
    expect(await within(dialog).findByRole("link", { name: "Aprila" })).toHaveAttribute("href", "/projects/acme/automation?id=30");
  });

  it("an expired trace says so", async () => {
    api({
      "GET /conversations/3/messages": [answer(1, "Fatto.", "run-old")],
      "GET /messages/1/learn-draft": () => new Response(JSON.stringify({ detail: "La traccia di questa risposta è scaduta" }), { status: 404 }),
    });
    renderTask();
    await pickOperator();
    fireEvent.click(await screen.findByRole("button", { name: /Giusto: fanne un'automation/ }));
    expect(await screen.findByText(/è scaduta/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Annulla" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("settings and automations with fields", () => {
  it("the settings save the allowed commands, a detected one and the Operator", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...DEV, ...(await request.json()) }));
    api({
      "GET /projects/acme/dev-settings": { ...DEV, allowed_commands: ["uv sync"], suggested_commands: ["mvn -B clean install"] },
      "PUT /projects/acme/dev-settings": saved,
      "GET /projects/acme/data-settings": { visible_note_types: ["generic"], files_visible: true, due_soon_days: 3 },
    });
    renderPage(<Routes>{projectRoutes()}</Routes>, { route: "/projects/acme/project?tab=settings" });
    fireEvent.click(await screen.findByRole("button", { name: /🧪 Verifiche dello sviluppo/ }));
    fireEvent.click(await screen.findByRole("button", { name: /⚙️ Verifiche dello sviluppo/ }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.click(await within(dialog).findByRole("button", { name: /mvn -B clean install/ }));
    fireEvent.click(within(dialog).getByRole("textbox", { name: "Operatore della preparazione" }));
    fireEvent.click(await screen.findByRole("option", { name: "Operatore Java" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ allowed_commands: ["uv sync", "mvn -B clean install"], operator_chatbot_id: 12 });
  });

  it("an automation with fields asks them to run and sends them as JSON", async () => {
    const enqueued = vi.fn(async (request: Request) => ({ id: 1, pipeline_id: 21, status: "queued", ...(await request.json()), output: null, error: null,
                                                         created_at: "2026-11-13T10:00:00Z", started_at: null, finished_at: null, steps: [] }));
    mockApi({
      "GET /projects/acme/pipelines": [{ ...LEARNED, fields: ["branch"] }],
      "GET /pipelines/21/runs": [],
      "POST /pipelines/21/runs": enqueued,
      "GET /admin/worker": { workers: [] },
    });
    renderPage(<Routes><Route path="/projects/:project/automation" element={<AutomationTab />} /></Routes>, { route: "/projects/acme/automation?id=21" });
    fireEvent.change(await screen.findByLabelText(/branch/), { target: { value: "feature/x" } });
    fireEvent.click(screen.getByRole("button", { name: /Esegui/ }));
    await waitFor(() => expect(enqueued).toHaveBeenCalled());
    expect(await enqueued.mock.results[0].value).toMatchObject({ input: JSON.stringify({ branch: "feature/x" }) });
  });
});
