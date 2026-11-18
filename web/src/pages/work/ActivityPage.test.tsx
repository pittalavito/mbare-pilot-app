import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";
import { stepOf } from "./ActivityPage";

/** Plan 18, an activity in steps: Descrivi → Pianifica → Lavora → Chiudi. */

afterEach(() => vi.unstubAllGlobals());

const ACTIVITY = {
  name: "attivita-login.md", title: "Login sicuro", status: "todo", description: "OTP per tutti", references: [],
  items: [{ text: "Capire il flusso", done: false }, { text: "Chiedere l'OTP", done: false }], agent_tasks: [],
};
const proposal = (id: number, title: string, extra = {}) => ({
  id, title, type: "development", repository: "", items: [], item_texts: [], new: false, reason: "", objective: "", criteria: [], ...extra,
});
const PLAN: Record<string, unknown> = {
  id: 3, project_name: "acme", activity: ACTIVITY.name, run_id: "r", tasks: [], proposals: [], cost_eur: 0.0012, paused: true, prepare: "dev",
  skipped: [], errors: {}, after_automation: null, automation_runs: {}, auto_approve: false, approved: [],
  created_at: "2026-11-13T10:00:00Z", updated_at: "2026-11-13T10:00:00Z",
};
const step = (key: string, label: string, state: string, detail = "") => ({ key, label, state, detail });
const TASK = (name: string, title: string, steps: ReturnType<typeof step>[], extra = {}) => ({
  task: name, title, type: "development", status: "todo", repository: "api", session_id: null, steps, current: false, ...extra,
});
const AGENT_TASK = { name: "agent-task-otp.md", title: "Login con OTP", status: "to_verify", type: "development", objective: "OTP", context: "",
  criteria: [], constraints: "", references: [] };

function api(path: unknown, extra: Record<string, unknown> = {}, activity: object = ACTIVITY) {
  mockApi({
    ...PROJECT_API,
    "GET /projects/acme/activities": [activity],
    "GET /projects/acme/activities/attivita-login.md/path": path,
    "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }, { path: "lib", name: "lib" }],
    ...extra,
  });
}

const renderAt = (query = "") => renderPage(<Routes>{projectRoutes()}</Routes>, { route: `/projects/acme/work?note=${ACTIVITY.name}${query}` });
const body = async (mock: ReturnType<typeof vi.fn>, index = 0) => mock.mock.results[index].value;

describe("the step comes from where the activity is", () => {
  it("derives it", () => {
    const task = TASK("t", "T", [], { current: true });
    expect(stepOf(ACTIVITY as never, { plan: null, tasks: [], summary: "" } as never)).toBe("describe");
    expect(stepOf(ACTIVITY as never, { plan: { ...PLAN, proposals: [proposal(1, "A")] }, tasks: [], summary: "" } as never)).toBe("plan");
    expect(stepOf(ACTIVITY as never, { plan: PLAN, tasks: [task], summary: "" } as never)).toBe("work");
    expect(stepOf(ACTIVITY as never, { plan: PLAN, tasks: [{ ...task, current: false, status: "done" }], summary: "" } as never)).toBe("close");
    expect(stepOf({ ...ACTIVITY, status: "done" } as never, undefined)).toBe("close");
  });
});

describe("1. Descrivi", () => {
  it("saves description and items, then goes on to Pianifica (no status to choose)", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...ACTIVITY, ...(await request.json()) }));
    api({ plan: null, tasks: [], summary: "" }, { "PUT /projects/acme/activities/attivita-login.md": saved });
    renderAt();

    expect(await screen.findByRole("tab", { name: /Descrivi/, selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Lavora/ })).toBeDisabled(); // no tasks yet
    expect(screen.queryByRole("radiogroup", { name: /Stato/ })).not.toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText(/^Descrizione/), { target: { value: "OTP via SMS" } });
    fireEvent.click(screen.getByRole("button", { name: "Avanti: Pianifica →" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await body(saved)).toMatchObject({ description: "OTP via SMS" });
    expect(await screen.findByRole("tab", { name: /Pianifica/, selected: true })).toBeInTheDocument();
  });
});

describe("2. Pianifica", () => {
  it("asks the Pianificatore, corrects and orders the rows, adds one by hand and creates the tasks «da fare»", async () => {
    let plan = { ...PLAN };
    const proposed = vi.fn(() => {
      plan = { ...PLAN, proposals: [proposal(1, "Aggiorna la libreria", { new: true, repository: "lib", objective: "Alla 2.0", reason: "serve prima" }),
        proposal(2, "Login con OTP", { items: [2], item_texts: ["Chiedere l'OTP"], repository: "api" })] };
      return plan;
    });
    const confirmed = vi.fn(async (request: Request) => ({ ...plan, proposals: [], body: await request.json() }));
    api(() => ({ plan, tasks: [], summary: "" }), {
      "POST /projects/acme/activities/attivita-login.md/plan": proposed,
      "POST /projects/acme/activities/attivita-login.md/plan/confirm": confirmed,
    });
    renderAt("&step=plan");

    fireEvent.click(await screen.findByRole("button", { name: /✨ Proponi i task/ }));
    expect(await screen.findByDisplayValue("Aggiorna la libreria")).toBeInTheDocument();
    expect(screen.getByText("nuovo")).toBeInTheDocument();
    expect(screen.getByText("voci 2")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "▸ dettagli" })[0]);
    expect(screen.getByText("💡 serve prima")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Giù" })[0]); // the library after the login
    fireEvent.click(screen.getByRole("button", { name: "➕ Task" }));
    const rows = screen.getAllByTestId("plan-row");
    fireEvent.change(within(rows[2]).getByLabelText("Titolo del task"), { target: { value: "Capire il flusso" } });
    fireEvent.click(within(rows[2]).getByRole("textbox", { name: "Voci che copre" }));
    fireEvent.click(await screen.findByRole("option", { name: "1. Capire il flusso" }));
    fireEvent.click(screen.getByRole("button", { name: "Crea 3 task" }));

    await waitFor(() => expect(confirmed).toHaveBeenCalled());
    expect((await body(confirmed)).body.choices).toEqual([
      expect.objectContaining({ id: 2, title: "Login con OTP", repository: "api", items: [] }),
      expect.objectContaining({ id: 1, title: "Aggiorna la libreria", objective: "Alla 2.0" }),
      expect.objectContaining({ id: null, title: "Capire il flusso", items: [1] }),
    ]);
  });

  it("with tasks already there: shows them, «Proponi altri task», drops the proposals", async () => {
    const dismissed = vi.fn(() => PLAN);
    api({ plan: { ...PLAN, proposals: [proposal(1, "Test di carico")] }, tasks: [TASK("agent-task-a.md", "Login con OTP", [], { status: "done" })], summary: "" }, {
      "POST /projects/acme/activities/attivita-login.md/plan/dismiss": dismissed,
    });
    renderAt("&step=plan");

    expect(await screen.findByText("Task già creati")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Proponi altri task/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Scarta le proposte" }));
    await waitFor(() => expect(dismissed).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Avanti: Lavora →" })).toBeInTheDocument();
  });
});

describe("3. Lavora", () => {
  const working = (steps: ReturnType<typeof step>[], extra = {}) => ({
    plan: PLAN, summary: "",
    tasks: [TASK(AGENT_TASK.name, "Login con OTP", steps, { current: true, ...extra }), TASK("agent-task-b.md", "Analizza", [], { type: "analysis", repository: "" })],
  });

  it("Avvia, the settings of the round and a row that shows its Copilot chat in the panel", async () => {
    const paused = vi.fn(async (request: Request) => ({ ...PLAN, ...(await request.json()) }));
    const options = vi.fn(async (request: Request) => ({ ...PLAN, ...(await request.json()) }));
    api(working([step("prepare", "Preparazione", "todo"), step("delegate", "Delega a Copilot", "todo")]), {
      "POST /projects/acme/activities/attivita-login.md/plan/pause": paused,
      "POST /projects/acme/activities/attivita-login.md/plan/options": options,
      "GET /projects/acme/pipelines": [{ id: 21, project_name: "acme", name: "Prepara stack", description: "", active: true, fields: [], purpose: "prepare",
        steps: [{ name: "S" }], edges: [] }],
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt();

    expect(await screen.findByRole("tab", { name: /Lavora/, selected: true })).toBeInTheDocument();
    expect(screen.getByText(/Pronto\. Premi «▶️ Avvia»/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🤖 Delega a mano" })).toBeInTheDocument(); // paused: by hand
    fireEvent.click(screen.getByRole("button", { name: "▶️ Avvia" }));
    await waitFor(() => expect(paused).toHaveBeenCalled());
    expect(await body(paused)).toMatchObject({ paused: false });

    fireEvent.click(screen.getByRole("textbox", { name: "Prima di delegare a Copilot" }));
    fireEvent.click(await screen.findByRole("option", { name: "Automation: Prepara stack" }));
    await waitFor(() => expect(options).toHaveBeenCalled());
    expect(await body(options)).toMatchObject({ prepare: "automation:21", after_automation: null, auto_approve: false });
    fireEvent.click(screen.getByRole("switch", { name: /Parti senza chiedermi l'ok/ }));
    await waitFor(() => expect(options).toHaveBeenCalledTimes(2));
    expect(await body(options, 1)).toMatchObject({ auto_approve: true });

    fireEvent.click(screen.getAllByTestId("work-task")[1]);
    await waitFor(() => expect(screen.getAllByTestId("work-task")[1]).toHaveAttribute("aria-selected", "true"));
  });

  it("the fields of Prepara sviluppo as a template, a task's own fields, and the worker that is stopped", async () => {
    const options = vi.fn(async (request: Request) => ({ ...PLAN, ...(await request.json()) }));
    const savedFields = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    const started = vi.fn(() => ({ status: "running", pid: 1, workers: [] }));
    api(working([step("prepare", "Preparazione", "todo"), step("delegate", "Delega a Copilot", "todo")]), {
      "POST /projects/acme/activities/attivita-login.md/plan/options": options,
      "GET /projects/acme/activities/attivita-login.md/plan/fields": (request: Request) => ({
        task: new URL(request.url).searchParams.get("task"), step: "prepare", automation: "Prepara sviluppo", own: false,
        fields: { branch: "feature/otp", base: "develop" },
      }),
      "PUT /projects/acme/activities/attivita-login.md/plan/fields": savedFields,
      "GET /admin/worker": { status: "stopped", pid: null, workers: [] },
      "POST /admin/worker/start": started,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    expect(await screen.findByText("Il worker è fermo: il giro non parte")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Avvia il worker" }));
    await waitFor(() => expect(started).toHaveBeenCalled());

    const branch = screen.getByRole("textbox", { name: "branch" });
    expect(branch).toHaveValue("feature/{task}");
    expect(screen.getByRole("textbox", { name: "base" })).toHaveValue("{base}");
    fireEvent.change(branch, { target: { value: "feat/{task}" } });
    fireEvent.blur(branch);
    await waitFor(() => expect(options).toHaveBeenCalled());
    expect(await body(options)).toMatchObject({ prepare: "dev", prepare_fields: { branch: "feat/{task}", base: "{base}" } });

    fireEvent.click(screen.getAllByRole("button", { name: "⚙️ Campi" })[0]);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByDisplayValue("feature/otp")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByDisplayValue("feature/otp"), { target: { value: "hotfix/otp" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Salva per questo task" }));
    await waitFor(() => expect(savedFields).toHaveBeenCalled());
    expect((await body(savedFields)).body).toEqual({ task: AGENT_TASK.name, step: "prepare", fields: { branch: "hotfix/otp", base: "develop" } });
  });

  it("a failed verification: you decide (send back, retry the tests, skip)", async () => {
    const retried = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    api(working([step("delegate", "Delega a Copilot", "done"), step("copilot_plan", "Piano di Copilot", "done"), step("execution", "Esecuzione", "done"),
      step("verify", "Verifica", "failed", "test falliti"), step("final", "Conferma finale", "you")], { status: "to_verify", session_id: 4 }), {
      "POST /projects/acme/activities/attivita-login.md/plan/retry": retried,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    expect(await screen.findByRole("button", { name: "⏭ Salta" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "↩ Rimanda a Copilot" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "🔁 Riprova i test" }));
    await waitFor(() => expect(retried).toHaveBeenCalled());
    expect((await body(retried)).body).toEqual({ task: AGENT_TASK.name, step: "verify" });
  });

  it("«Controlla e conferma» makes the task done", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...AGENT_TASK, ...(await request.json()) }));
    api(working([step("verify", "Verifica", "done"), step("final", "Conferma finale", "you")], { status: "to_verify" }), {
      "GET /projects/acme/agent-tasks": [AGENT_TASK],
      [`PUT /projects/acme/agent-tasks/${AGENT_TASK.name}`]: saved,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    fireEvent.click(await screen.findByRole("button", { name: "✅ Controlla e conferma" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await body(saved)).toMatchObject({ status: "done", title: "Login con OTP" });
  });
});

describe("4. Chiudi", () => {
  const DONE_PATH = { plan: PLAN, tasks: [TASK(AGENT_TASK.name, "Login con OTP", [], { status: "done" })], summary: "Task fatti: 1 di 1\nCosto: …" };

  it("proposes what was learned, warns about what is open, closes", async () => {
    const proposed = vi.fn(() => ({ points: ["lib-auth prima dell'api"], run_id: "r", cost_eur: 0.0002 }));
    const closed = vi.fn(async (request: Request) => ({ activity: ACTIVITY.name, context: "imparato.md", index_error: null, body: await request.json() }));
    api(DONE_PATH, {
      "POST /projects/acme/activities/attivita-login.md/learned": proposed,
      "POST /projects/acme/activities/attivita-login.md/close": closed,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt();

    expect(await screen.findByRole("tab", { name: /Chiudi/, selected: true })).toBeInTheDocument();
    expect(screen.getByTestId("close-summary")).toHaveTextContent("Task fatti: 1 di 1");
    fireEvent.click(screen.getByRole("button", { name: /Proponi cosa ho imparato/ }));
    expect(await screen.findByDisplayValue("- lib-auth prima dell'api")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "✅ Chiudi attività" }));
    expect(await screen.findByText(/Voci non fatte: Capire il flusso, Chiedere l'OTP/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Chiudi lo stesso" }));

    await waitFor(() => expect(closed).toHaveBeenCalled());
    expect((await body(closed)).body).toEqual({ learned: "- lib-auth prima dell'api" });
  });

  it("a closed activity says where the learning is and can be reopened", async () => {
    const reopened = vi.fn(() => new Response(null, { status: 204 }));
    api(DONE_PATH, { "POST /projects/acme/activities/attivita-login.md/reopen": reopened }, { ...ACTIVITY, status: "done" });
    renderAt();

    expect(await screen.findByText(/context\/imparato.md/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "↩ Riapri" }));
    await waitFor(() => expect(reopened).toHaveBeenCalled());
  });
});
