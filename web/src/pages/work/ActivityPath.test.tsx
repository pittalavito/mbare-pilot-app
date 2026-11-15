import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";

/** Plan 12a, «▶️ Lavora attività»: the Pianificatore's proposals in the activity
 * (keep, correct, order, create), then the path with the button where it is the user's turn. */

afterEach(() => vi.unstubAllGlobals());

const ACTIVITY = {
  name: "attivita-login.md", title: "Login sicuro", status: "in_progress", description: "", learned: "", references: [],
  items: [{ text: "Chiedere l'OTP", done: false }], agent_tasks: [],
};
const proposal = (id: number, title: string, extra = {}) => ({
  id, title, type: "development", repository: "", items: [], item_texts: [], new: false, reason: "", objective: "", criteria: [], ...extra,
});
const PLAN = {
  id: 3, project_name: "acme", activity: ACTIVITY.name, run_id: "r", status: "proposed", tasks: [], cost_eur: 0.0012,
  created_at: "2026-11-13T10:00:00Z", updated_at: "2026-11-13T10:00:00Z",
  proposals: [
    proposal(1, "Aggiorna la libreria", { new: true, repository: "lib", reason: "serve prima", objective: "Alla 2.0", criteria: ["build ok"] }),
    proposal(2, "Login con OTP", { items: [1], item_texts: ["Chiedere l'OTP"], repository: "api", objective: "OTP" }),
    proposal(3, "Analizza", { type: "analysis" }),
  ],
};
const step = (key: string, label: string, state: string, detail = "") => ({ key, label, state, detail });
const TASK = (name: string, title: string, steps: ReturnType<typeof step>[], extra = {}) => ({
  task: name, title, type: "development", status: "refinement", repository: "api", session_id: null, steps, current: false, ...extra,
});

function api(path: unknown, extra: Record<string, unknown> = {}) {
  mockApi({
    ...PROJECT_API,
    "GET /projects/acme/activities": [ACTIVITY],
    "GET /projects/acme/activities/attivita-login.md/path": path,
    "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }, { path: "lib", name: "lib" }],
    ...extra,
  });
}

const renderActivity = () => renderPage(<Routes>{projectRoutes()}</Routes>, { route: `/projects/acme/work?note=${ACTIVITY.name}` });

const CONFIRMED = { ...PLAN, status: "confirmed", paused: false, prepare: "", skipped: [], errors: {}, retries: {} };

describe("the path that moves by itself (12b)", () => {
  it("pauses, resumes and chooses how to prepare", async () => {
    const paused = vi.fn(async (request: Request) => ({ ...CONFIRMED, ...(await request.json()) }));
    const prepared = vi.fn(async (request: Request) => ({ ...CONFIRMED, ...(await request.json()) }));
    api({ plan: CONFIRMED, tasks: [TASK("agent-task-a.md", "A", [step("confirm", "Conferma del task", "done"), step("prepare", "Preparazione", "todo"),
                                                                    step("delegate", "Delega a Copilot", "todo")], { current: true })] }, {
      "POST /projects/acme/activities/attivita-login.md/plan/pause": paused,
      "POST /projects/acme/activities/attivita-login.md/plan/prepare": prepared,
      "GET /projects/acme/pipelines": [{ id: 21, project_name: "acme", name: "Prepara feature", description: "", active: true, fields: [],
                                         purpose: "prepare", steps: [], edges: [] }],
      "GET /projects/acme/dev-settings": { test_scope: "all", prepare_automation: true, verify_automation: false, repositories: [], auto_retries: 1,
                                           allowed_commands: [], suggested_commands: [], operator_chatbot_id: null },
    });
    renderActivity();
    expect(await screen.findByText(/Il giro lo prepara e lo delega a breve/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delega a Copilot/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Pausa/ }));
    await waitFor(() => expect(paused).toHaveBeenCalled());
    expect(await paused.mock.results[0].value).toMatchObject({ paused: true });

    fireEvent.click(screen.getByRole("textbox", { name: "Preparazione del giro" }));
    fireEvent.click(await screen.findByRole("option", { name: /Prepara feature \(imparata\)/ }));
    await waitFor(() => expect(prepared).toHaveBeenCalled());
    expect(await prepared.mock.results[0].value).toMatchObject({ prepare: "learned:21" });
  });

  it("a failed preparation offers retry, the Operator and skip", async () => {
    const bodies: Record<string, unknown[]> = { retry: [], skip: [] };
    const record = (key: string) => async (request: Request) => { bodies[key].push(await request.json()); return CONFIRMED; };
    api({ plan: CONFIRMED, tasks: [TASK("agent-task-a.md", "A", [step("confirm", "Conferma del task", "done"),
                                                               step("prepare", "Preparazione", "failed", "Modifiche non committate")], { current: true })] }, {
      "POST /projects/acme/activities/attivita-login.md/plan/retry": record("retry"),
      "POST /projects/acme/activities/attivita-login.md/plan/skip": record("skip"),
      "GET /projects/acme/chatbots": [{ id: 12, project_name: "acme", name: "Operatore Java", kind: "operator", description: "", system_prompt: "x",
                                        prompt_version: 1, model: "m", max_steps: 4, tool_names: [], automation_cache: false }],
      "GET /chatbots/12/conversations": [],
    });
    renderActivity();
    expect(await screen.findByText("Modifiche non committate")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Riprova/ }));
    await waitFor(() => expect(bodies.retry).toEqual([{ task: "agent-task-a.md", step: "prepare" }]));
    fireEvent.click(screen.getByRole("button", { name: /Salta/ }));
    await waitFor(() => expect(bodies.skip).toEqual([{ task: "agent-task-a.md", step: "prepare" }]));
    fireEvent.click(screen.getByRole("button", { name: /Fallo fare all'Operatore/ }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Agente" })).toHaveValue("Operatore Java"));
    expect((screen.getByPlaceholderText(/Scrivi a Operatore Java/) as HTMLTextAreaElement).value).toContain("Modifiche non committate");
  });

  it("a failed delegation can be retried or done by hand, a failed verification retried", async () => {
    api({ plan: CONFIRMED, tasks: [
      TASK("agent-task-a.md", "A", [step("delegate", "Delega a Copilot", "failed", "Copilot non c'è")], { current: true }),
      TASK("agent-task-b.md", "B", [step("verify", "Verifica", "failed", "test falliti, rimandato a Copilot 1 volte")], { current: true }),
    ] });
    renderActivity();
    expect(await screen.findByRole("button", { name: /Delega a mano/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Riprova/ })).toHaveLength(2);
    expect(screen.getByText(/rimandato a Copilot 1 volte/)).toBeInTheDocument();
  });
});

describe("automations, automatic ok and summary (12c)", () => {
  const AUTOMATIONS = [{ id: 31, project_name: "acme", name: "Coverage", description: "", active: true, fields: [], purpose: "",
                         steps: [{ name: "x", kind: "function" }], edges: [] }];

  it("chooses the automations before and after each task and the automatic ok", async () => {
    const bodies: unknown[] = [];
    api({ plan: CONFIRMED, tasks: [TASK("agent-task-a.md", "A", [step("confirm", "Conferma del task", "done"), step("before", "Automation prima", "todo")],
                                        { current: true })] }, {
      "GET /projects/acme/pipelines": AUTOMATIONS,
      "POST /projects/acme/activities/attivita-login.md/plan/options": async (request: Request) => { bodies.push(await request.json()); return CONFIRMED; },
    });
    renderActivity();
    expect(await screen.findByText(/lancia l'automation prima del task/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("textbox", { name: "Dopo ogni task" }));
    fireEvent.click(await screen.findByRole("option", { name: "Coverage" }));
    await waitFor(() => expect(bodies[0]).toEqual({ before_automation: null, after_automation: 31, auto_approve: false }));
    fireEvent.click(screen.getByRole("switch", { name: /senza chiedermi l'ok/ }));
    await waitFor(() => expect(bodies[1]).toMatchObject({ auto_approve: true }));
  });

  it("«Chiedi all'Architetto» opens the zone Automation with the request ready", async () => {
    api({ plan: CONFIRMED, tasks: [TASK("agent-task-a.md", "A", [step("confirm", "Conferma del task", "you")], { current: true })] }, {
      "GET /projects/acme/pipelines": AUTOMATIONS,
      "GET /projects/acme/chatbots": [{ id: 5, project_name: "acme", name: "Architetto", kind: "automation", description: "", system_prompt: "x",
                                        prompt_version: 1, model: "m", max_steps: 4, tool_names: [], automation_cache: false }],
      "GET /chatbots/5/conversations": [],
      "GET /functions": [], "GET /admin/worker": { workers: [] },
    });
    renderActivity();
    fireEvent.click(await screen.findByRole("textbox", { name: "Prima di ogni task" }));
    fireEvent.click(await screen.findByRole("option", { name: /Chiedi all'Architetto/ }));
    await waitFor(() => expect((screen.getByPlaceholderText(/Scrivi a Architetto/) as HTMLTextAreaElement).value)
      .toContain("prima ogni task di sviluppo dell'attività attivita-login.md"));
  });

  it("a failed automation step offers retry and skip; the summary goes in «Imparato»", async () => {
    api({ plan: CONFIRMED, summary: "Fatto con «▶️ Lavora attività» (1 di 1 task):\n- ✓ A (sviluppo)", tasks: [
      TASK("agent-task-a.md", "A", [step("after", "Automation dopo", "failed", "coverage bassa")], { current: true }),
    ] });
    renderActivity();
    expect(await screen.findByText("coverage bassa")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Riprova/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Salta/ })).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId("path-summary")).getByRole("button", { name: /Metti in Imparato/ }));
    await waitFor(() => expect(screen.getByLabelText("Imparato")).toHaveValue("Fatto con «▶️ Lavora attività» (1 di 1 task):\n- ✓ A (sviluppo)"));
  });
});

describe("«▶️ Lavora attività»", () => {
  it("asks the Pianificatore for the plan", async () => {
    const proposed = vi.fn(() => PLAN);
    api({ plan: null, tasks: [] }, { "POST /projects/acme/activities/attivita-login.md/plan": proposed });
    renderActivity();
    fireEvent.click(await screen.findByRole("button", { name: /Lavora attività/ }));
    await waitFor(() => expect(proposed).toHaveBeenCalled());
  });

  it("the proposals are kept, corrected and ordered, then become the tasks", async () => {
    const confirmed = vi.fn(async (request: Request) => ({ ...PLAN, status: "confirmed", ...(await request.json()) }));
    api({ plan: PLAN, tasks: [] }, { "POST /projects/acme/activities/attivita-login.md/plan/confirm": confirmed });
    renderActivity();

    const cards = await screen.findAllByTestId("plan-proposal");
    expect(within(cards[0]).getByText("nuovo")).toBeInTheDocument();
    expect(within(cards[0]).getByText(/serve prima/)).toBeInTheDocument();
    expect(within(cards[1]).getByText(/Dalle voci: Chiedere l'OTP/)).toBeInTheDocument();
    expect(screen.getByText(/0,0012/)).toBeInTheDocument();
    fireEvent.click(within(cards[2]).getByLabelText("Tieni Analizza"));
    fireEvent.change(within(cards[1]).getByLabelText("Titolo del task"), { target: { value: "Login OTP" } });
    fireEvent.change(within(cards[1]).getByLabelText("Criteri"), { target: { value: "test verdi\n\n" } });
    fireEvent.click(within(cards[1]).getByLabelText("Su"));
    fireEvent.click(screen.getByRole("button", { name: "Crea 2 task" }));

    await waitFor(() => expect(confirmed).toHaveBeenCalled());
    expect(await confirmed.mock.results[0].value).toMatchObject({ choices: [
      { id: 2, title: "Login OTP", repository: "api", objective: "OTP", criteria: ["test verdi"] },
      { id: 1, title: "Aggiorna la libreria", repository: "lib", criteria: ["build ok"] },
    ] });
  });

  it("a plan can be dismissed", async () => {
    const dismissed = vi.fn(() => ({ ...PLAN, status: "dismissed" }));
    api({ plan: { ...PLAN, proposals: [] }, tasks: [] }, { "POST /projects/acme/activities/attivita-login.md/plan/dismiss": dismissed });
    renderActivity();
    expect(await screen.findByText(/Nessun task proposto/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Scarta" }));
    await waitFor(() => expect(dismissed).toHaveBeenCalled());
  });

  it("the path shows each task's steps and the button where it is your turn", async () => {
    const confirmedTask = vi.fn(() => new Response(null, { status: 204 }));
    api({
      plan: { ...PLAN, status: "confirmed" },
      tasks: [
        TASK("agent-task-lib.md", "Aggiorna la libreria", [step("confirm", "Conferma del task", "you"), step("delegate", "Preparazione e delega", "todo")],
             { current: true, repository: "lib" }),
        TASK("agent-task-login.md", "Login", [step("confirm", "Conferma del task", "done"), step("delegate", "Preparazione e delega", "todo")]),
      ],
    }, {
      "POST /projects/acme/agent-tasks/agent-task-lib.md/confirm": confirmedTask,
      "GET /projects/acme/dev-settings": { test_scope: "all", prepare_automation: false, verify_automation: false, repositories: [],
                                           allowed_commands: [], suggested_commands: [], operator_chatbot_id: null },
    });
    renderActivity();

    expect(await screen.findByText(/Percorso · 0 di 2 task fatti/)).toBeInTheDocument();
    const [first, second] = screen.getAllByTestId("path-task");
    expect(within(first).getByText(/👤 Conferma del task/)).toBeInTheDocument();
    expect(within(second).queryByRole("button", { name: /Conferma il task/ })).not.toBeInTheDocument(); // not its turn yet
    fireEvent.click(within(first).getByRole("button", { name: /Conferma il task/ }));
    await waitFor(() => expect(confirmedTask).toHaveBeenCalled());
  });

  it("paused, delegating from the path proposes the plan's repository", async () => {
    api({
      plan: { ...PLAN, status: "confirmed", paused: true },
      tasks: [TASK("agent-task-lib.md", "Libreria", [step("confirm", "Conferma del task", "done"), step("delegate", "Preparazione e delega", "todo")],
                   { current: true, repository: "lib", status: "todo" })],
    }, {
      "GET /copilot/status": { installed: true, version: "x", prompts: [], default_model: "", models: [] },
      "GET /projects/acme/agent-tasks": [{ name: "agent-task-lib.md", title: "Libreria", status: "todo", type: "development", objective: "o",
                                           context: "", criteria: [], constraints: "", references: [], tests: null }],
      "GET /projects/acme/git/branches": { current: "main", local: ["main"], remote: [] },
    });
    renderActivity();
    fireEvent.click(await screen.findByRole("button", { name: /Delega a Copilot/ }));
    expect(await within(await screen.findByRole("dialog")).findByDisplayValue("lib")).toBeInTheDocument();
  });

  it("Copilot's turn, a failure and the final check open the task", async () => {
    api({
      plan: { ...PLAN, status: "confirmed" },
      tasks: [
        TASK("agent-task-a.md", "A", [step("copilot_plan", "Piano di Copilot", "you")], { current: true }),
        TASK("agent-task-b.md", "B", [step("execution", "Esecuzione", "failed", "crash")], { current: true }),
        TASK("agent-task-c.md", "C", [step("final", "Conferma finale", "you")], { current: true }),
        TASK("agent-task-d.md", "D", [], { status: "missing" }),
      ],
    });
    renderActivity();
    expect(await screen.findByRole("button", { name: /Rispondi a Copilot/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apri il task" })).toBeInTheDocument();
    expect(screen.getByText("cancellato")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Controlla e conferma/ }));
  });
});
