import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";
import { stepOf } from "./ActivityPage";

/** Plan 18, an activity in steps: Descrivi → Pianifica → Lavora → Chiudi;
 * plan 22: pre/post development tasks (Dev or by hand, «Fatto») and «Apri». */

afterEach(() => vi.unstubAllGlobals());

const ACTIVITY = {
  name: "attivita-login.md", title: "Login sicuro", status: "todo", description: "OTP per tutti", references: [],
  items: [{ text: "Capire il flusso", done: false }, { text: "Chiedere l'OTP", done: false }], agent_tasks: [],
};
const proposal = (id: number, title: string, extra = {}) => ({
  id, title, type: "development", repository: "", items: [], item_texts: [], new: false, reason: "", objective: "", criteria: [], ...extra,
});
const PLAN: Record<string, unknown> = {
  id: 3, project_name: "acme", activity: ACTIVITY.name, run_id: "r", tasks: [], proposals: [], cost_eur: 0.0012, paused: true,
  errors: {}, auto_approve: false, approved: [],
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

  it("Avvia, the automatic ok, «Apri» towards the task and a row that shows its Copilot chat in the panel", async () => {
    const paused = vi.fn(async (request: Request) => ({ ...PLAN, ...(await request.json()) }));
    const options = vi.fn(async (request: Request) => ({ ...PLAN, ...(await request.json()) }));
    api(working([step("delegate", "Delega a Copilot", "todo")]), {
      "POST /projects/acme/activities/attivita-login.md/plan/pause": paused,
      "POST /projects/acme/activities/attivita-login.md/plan/options": options,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt();

    expect(await screen.findByRole("tab", { name: /Lavora/, selected: true })).toBeInTheDocument();
    expect(screen.getByText(/Pronto\. Premi «▶️ Avvia»/)).toBeInTheDocument();
    expect(screen.queryByText("Prima di delegare a Copilot")).not.toBeInTheDocument(); // plan 22: pre/post development tasks instead
    expect(screen.getByRole("button", { name: "🤖 Delega a mano" })).toBeInTheDocument(); // paused: by hand
    fireEvent.click(screen.getByRole("button", { name: "▶️ Avvia" }));
    await waitFor(() => expect(paused).toHaveBeenCalled());
    expect(await body(paused)).toMatchObject({ paused: false });

    fireEvent.click(screen.getByRole("switch", { name: /Parti senza chiedermi l'ok/ }));
    await waitFor(() => expect(options).toHaveBeenCalled());
    expect(await body(options)).toMatchObject({ auto_approve: true });

    expect(screen.getAllByRole("link", { name: "Apri" })[0]).toHaveAttribute("href",
      `/projects/acme/work?note=${AGENT_TASK.name}&from=${ACTIVITY.name}`);
    fireEvent.click(screen.getAllByTestId("work-task")[1]);
    await waitFor(() => expect(screen.getAllByTestId("work-task")[1]).toHaveAttribute("aria-selected", "true"));
  });

  it("the worker that is stopped can be started", async () => {
    const started = vi.fn(() => ({ status: "running", pid: 1, workers: [] }));
    api(working([step("delegate", "Delega a Copilot", "todo")]), {
      "GET /admin/worker": { status: "stopped", pid: null, workers: [] },
      "POST /admin/worker/start": started,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    expect(await screen.findByText("Il worker è fermo: il giro non parte")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Avvia il worker" }));
    await waitFor(() => expect(started).toHaveBeenCalled());
  });

  it("a Pre without commands: «Automatico» readies the request for Dev; «A mano» → «Fatto» closes it", async () => {
    const done = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    const pre = { ...AGENT_TASK, name: "agent-task-otp.md", title: "OTP", type: "development", status: "todo",
      pre: { steps: ["git checkout -b feature/otp"], commands: [], automation: "" }, post: { steps: [], commands: [], automation: "" } };
    api({ plan: PLAN, summary: "", tasks: [TASK(pre.name, pre.title, [step("pre", "Pre", "you"), step("delegate", "Delega a Copilot", "todo")], { current: true })] }, {
      "GET /projects/acme/agent-tasks": [pre],
      "GET /projects/acme/pipelines": [],
      "POST /projects/acme/activities/attivita-login.md/plan/done": done,
      "GET /projects/acme/chatbots": [{ id: 12, project_name: "acme", name: "Dev", kind: "operator", description: "", system_prompt: "x",
        prompt_version: 1, model: "mock/echo", max_steps: 12, tool_names: ["run_command"], automation_cache: false }],
      "GET /chatbots/12/conversations": [],
      "GET /projects/acme/command-requests": [],
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    fireEvent.click(await screen.findByRole("button", { name: "🤖 Automatico" }));
    expect(screen.queryByRole("button", { name: /Delega a mano/ })).not.toBeInTheDocument(); // never Copilot
    await waitFor(() => expect((screen.getByPlaceholderText(/Scrivi a Dev/) as HTMLTextAreaElement).value)
      .toBe("Fai il pre dello sviluppo «OTP» (agent-task-otp.md) sul repository api.\nPassi:\n- git checkout -b feature/otp\n"
        + "Alla fine dimmi in una riga cosa hai fatto."));

    fireEvent.click(screen.getByRole("button", { name: "✋ A mano" }));
    fireEvent.click(await screen.findByRole("button", { name: "✅ Fatto" }));
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect((await body(done)).body).toEqual({ task: pre.name, phase: "pre" });
  });

  it("«⏭ Salta» skips the Post; «Salta da solo pre e post vuoti» is an option of the round", async () => {
    const skipped = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    const options = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    const task = { ...AGENT_TASK, type: "development", status: "done", pre: { steps: [], commands: [], automation: "" }, post: { steps: [], commands: [], automation: "" } };
    api({ plan: PLAN, summary: "", tasks: [TASK(task.name, task.title, [step("final", "Conferma finale", "done"), step("post", "Post", "you")], { current: true })] }, {
      "GET /projects/acme/agent-tasks": [task],
      "GET /projects/acme/pipelines": [],
      "POST /projects/acme/activities/attivita-login.md/plan/skip": skipped,
      "POST /projects/acme/activities/attivita-login.md/plan/options": options,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    fireEvent.click(await screen.findByRole("button", { name: "⏭ Salta" }));
    await waitFor(() => expect(skipped).toHaveBeenCalled());
    expect((await body(skipped)).body).toEqual({ task: task.name, phase: "post" });
    fireEvent.click(screen.getByRole("switch", { name: "Salta da solo pre e post vuoti" }));
    await waitFor(() => expect(options).toHaveBeenCalled());
    expect((await body(options)).body).toEqual({ auto_skip_empty: true });
  });

  it("«Automatico» with commands asks the ok for the ones not allowed, then starts; the run's state and output show", async () => {
    const pre = { ...AGENT_TASK, name: "agent-task-build.md", title: "Build", type: "development", status: "done", pre: { steps: [], commands: [], automation: "" },
      post: { steps: [], commands: ["mvn -B clean install"], automation: "" } };
    let calls = 0;
    const sent: unknown[] = [];
    const auto = vi.fn(async (request: Request) => {
      sent.push(await request.json());
      calls += 1;
      return { plan: PLAN, pending_commands: calls === 1 ? ["mvn -B clean install"] : [] };
    });
    const answered = vi.fn(async (request: Request) => { expect(await request.json()).toEqual({ command: "mvn -B clean install", allow: true, always: false }); return null; });
    api({ plan: { ...PLAN, operations: { [`${pre.name}|post`]: { state: "failed", output: "$ mvn -B clean install\nBUILD FAILURE", error: "uscito con 1", pipeline_run_id: null } } },
      summary: "", tasks: [TASK(pre.name, pre.title, [step("post", "Post", "failed", "uscito con 1")], { current: true })] }, {
      "GET /projects/acme/agent-tasks": [pre],
      "GET /projects/acme/pipelines": [],
      "POST /projects/acme/activities/attivita-login.md/plan/auto": auto,
      "POST /projects/acme/command-requests/answer": answered,
      "GET /projects/acme/command-requests": [],
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    expect(await screen.findByText("uscito con 1")).toBeInTheDocument();
    expect(screen.getByText(/BUILD FAILURE/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "🤖 Automatico" }));
    expect(await screen.findByText("Comandi da permettere prima di partire")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Solo stavolta" }));
    await waitFor(() => expect(answered).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("Comandi da permettere prima di partire")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "🤖 Automatico" }));
    await waitFor(() => expect(auto).toHaveBeenCalledTimes(2));
    expect(sent[0]).toEqual({ task: pre.name, phase: "post" });
  });

  it("«A mano»: runs a command, an automation and reads the git status", async () => {
    const pre = { ...AGENT_TASK, name: "agent-task-build.md", title: "Build", type: "development", status: "todo",
      pre: { steps: [], commands: ["git pull"], automation: "Prova git" }, post: { steps: [], commands: [], automation: "" } };
    const run = vi.fn(async (request: Request) => {
      expect(await request.json()).toEqual({ repository: "api", command: "git pull" });
      return { allowed: true, exit_code: 0, output: "Già aggiornato." };
    });
    const enqueue = vi.fn(async (request: Request) => {
      expect(await request.json()).toEqual({ input: "api" });
      return { id: 9, pipeline_id: 4, status: "queued", input: "api", output: null, error: null, created_at: "2026-11-18T10:00:00Z", started_at: null, finished_at: null, steps: [] };
    });
    api({ plan: PLAN, summary: "", tasks: [TASK(pre.name, pre.title, [step("pre", "Pre", "you")], { current: true })] }, {
      "GET /projects/acme/agent-tasks": [pre],
      "GET /projects/acme/pipelines": [{ id: 4, project_name: "acme", name: "Prova git", description: "", active: true, steps: [], edges: [], fields: [], purpose: "general" }],
      "POST /projects/acme/commands/run": run,
      "POST /pipelines/4/runs": enqueue,
      "GET /pipelines/4/runs": [],
      "GET /projects/acme/git/status": { branch: "develop", upstream: null, ahead: 0, behind: 0, is_clean: true, changes: [] },
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    fireEvent.click(await screen.findByRole("button", { name: "✋ A mano" }));
    fireEvent.click(await screen.findByRole("button", { name: "Lancia git pull" }));
    expect(await screen.findByText("Già aggiornato.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "▶️ Lancia" }));
    await waitFor(() => expect(enqueue).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "🌿 Stato git" }));
    expect(await screen.findByText(/nessun file modificato/)).toBeInTheDocument();
  });

  it("a failed delegation can be retried", async () => {
    const retried = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    api(working([step("delegate", "Delega a Copilot", "failed", "Copilot non c'è")]), {
      "POST /projects/acme/activities/attivita-login.md/plan/retry": retried,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    expect(await screen.findByText("Copilot non c'è")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "🔁 Riprova" }));
    await waitFor(() => expect(retried).toHaveBeenCalled());
    expect((await body(retried)).body).toEqual({ task: AGENT_TASK.name, step: "delegate" });
  });

  it("«Controlla e conferma» makes the task done", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...AGENT_TASK, ...(await request.json()) }));
    api(working([step("execution", "Esecuzione", "done"), step("final", "Conferma finale", "you")], { status: "to_verify" }), {
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
    const proposed = vi.fn(() => ({ points: [{ theme: "Build", text: "lib-auth prima dell'api" }], run_id: "r", cost_eur: 0.0002 }));
    const closed = vi.fn(async (request: Request) => ({ activity: ACTIVITY.name, context: "imparato.md", index_error: null, body: await request.json() }));
    api(DONE_PATH, {
      "POST /projects/acme/activities/attivita-login.md/learned": proposed,
      "POST /projects/acme/activities/attivita-login.md/close": closed,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt();

    expect(await screen.findByRole("tab", { name: /Chiudi/, selected: true })).toBeInTheDocument();
    expect(screen.getByTestId("close-summary")).toHaveTextContent("Task fatti: 1 di 1");
    fireEvent.click(screen.getByRole("button", { name: /Proponi cosa ho imparato/ }));
    expect(await screen.findByDisplayValue("- Build: lib-auth prima dell'api")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "✅ Chiudi attività" }));
    expect(await screen.findByText(/Voci non fatte: Capire il flusso, Chiedere l'OTP/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Chiudi lo stesso" }));

    await waitFor(() => expect(closed).toHaveBeenCalled());
    expect((await body(closed)).body).toEqual({ learned: "- Build: lib-auth prima dell'api" });
  });

  it("a closed activity says where the learning is and can be reopened", async () => {
    const reopened = vi.fn(() => new Response(null, { status: 204 }));
    api(DONE_PATH, { "POST /projects/acme/activities/attivita-login.md/reopen": reopened }, { ...ACTIVITY, status: "done" });
    renderAt();

    expect(await screen.findByText(/context\/imparato.md/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "↩ Riapri" }));
    await waitFor(() => expect(reopened).toHaveBeenCalled());
  });

  it("«🗄 Archivia» deletes the references chosen and opens the archive (plan 33)", async () => {
    const archived = vi.fn(async (request: Request) => ({ note: "archivio-login-sicuro.md", deleted: [], body: await request.json() }));
    api(DONE_PATH, {
      "POST /projects/acme/activities/attivita-login.md/archive": archived,
      "GET /projects/acme/agent-tasks": [{ ...AGENT_TASK, status: "done", references: ["context-reference-pagina.md", "bozza-confluence-x.md"] }],
    }, { ...ACTIVITY, status: "done", agent_tasks: [AGENT_TASK.name], references: ["context-reference-arch.md"] });
    renderAt();

    fireEvent.click(await screen.findByRole("button", { name: "🗄 Archivia" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText("bozza-confluence-x.md")).not.toBeInTheDocument(); // drafts go anyway
    fireEvent.click(within(dialog).getByLabelText("context-reference-pagina.md"));
    fireEvent.click(within(dialog).getByRole("button", { name: "🗄 Archivia" }));
    await waitFor(() => expect(archived).toHaveBeenCalled());
    expect((await body(archived)).body).toEqual({ delete_references: ["context-reference-pagina.md"] });
  });
});

describe("plan 33: publish in the round and references in Pianifica", () => {
  it("a Confluence task with its draft saved shows «📤 Pubblica», with the draft editable", async () => {
    const page = { ...AGENT_TASK, name: "agent-task-pagina.md", title: "Pagina", type: "confluence", status: "to_verify", references: ["bozza-confluence-pagina.md"] };
    const published = vi.fn(async (request: Request) => ({ kind: "confluence", mode: "create", url: "u", reference: "r.md", draft: "", ...(await request.json()) }));
    api({ plan: PLAN, summary: "", tasks: [TASK(page.name, page.title, [step("answer", "Risposta di Copilot", "done"), step("publish", "Pubblica", "you")],
                                                  { type: "confluence", status: "to_verify", current: true })] }, {
      "GET /projects/acme/agent-tasks": [page],
      "GET /projects/acme/agent-tasks/agent-task-pagina.md/publish": { kind: "confluence", mode: "create", draft: "bozza-confluence-pagina.md", title: "Pagina",
        body: "Testo", unmasked: [], reference: null, target_title: "", target_body: "", target_url: "", space_key: "DOC", project_key: "" },
      "GET /projects/acme/atlassian/confluence/places": [],
      "POST /projects/acme/agent-tasks/agent-task-pagina.md/publish": published,
    }, { ...ACTIVITY, status: "in_progress" });
    renderAt("&step=work");

    expect(screen.queryByRole("button", { name: "✅ Conferma" })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /Pubblica su Confluence/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("tab", { name: /Modifica/ }));
    fireEvent.change(within(dialog).getByLabelText("Testo da pubblicare"), { target: { value: "Testo corretto" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Pubblica" }));
    await waitFor(() => expect(published).toHaveBeenCalled());
    expect(await published.mock.results[0].value).toMatchObject({ body: "Testo corretto", title: "" });
  });

  it("a proposal can drop some of the activity's references", async () => {
    const confirmed = vi.fn(async (request: Request) => ({ ...PLAN, body: await request.json() }));
    api({ plan: { ...PLAN, proposals: [proposal(1, "Login con OTP", { items: [2] })] }, summary: "", tasks: [] }, {
      "POST /projects/acme/activities/attivita-login.md/plan/confirm": confirmed,
    }, { ...ACTIVITY, references: ["context-reference-a.md", "context-reference-b.md"] });
    renderAt("&step=plan");

    fireEvent.click((await screen.findAllByRole("button", { name: "▸ dettagli" }))[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Togli context-reference-b.md" }));
    fireEvent.click(screen.getByRole("button", { name: /Crea 1 task/ }));
    await waitFor(() => expect(confirmed).toHaveBeenCalled());
    expect((await body(confirmed)).body.choices[0].references).toEqual(["context-reference-a.md"]);
  });
});
