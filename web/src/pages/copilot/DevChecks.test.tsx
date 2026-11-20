import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";

/** Blocco 09 and plan 34: the tests' settings, a development's
 * choice of tests (run_tests, Dev) and a task to verify sent back. */

afterEach(() => vi.unstubAllGlobals());

const TASK = {
  name: "agent-task-login.md", title: "Login", status: "to_verify", type: "development", objective: "o", context: "",
  criteria: [{ text: "c", done: false }], constraints: "", references: [], tests: null,
};
const SESSION = {
  id: 4, project_name: "acme", task_note: TASK.name, repository: "api", prompt: "", model: "", status: "done", cancel_requested: false,
  head_before: null, head_after: null, head_moved: false, changed_files: [], premium_requests: 1, error: null,
  created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z", started_at: null, finished_at: null,
};
const DEV = {
  test_scope: "all",
  repositories: [
    { repository: "api", kind: "python", detected_command: "uv run pytest", command: "" },
    { repository: "lib", kind: "maven", detected_command: "mvn -B test", command: "" },
  ],
};
const BRANCHES = {
  api: { current: "develop", local: ["develop", "main"], remote: ["origin/develop", "origin/main", "origin/HEAD"] },
  lib: { current: "main", local: ["main"], remote: ["origin/main", "origin/release"] },
};

function api(extra: Record<string, unknown> = {}) {
  const started = vi.fn(async (request: Request) => ({ ...SESSION, id: 9, status: "planning", ...(await request.json()) }));
  const savedTask = vi.fn(async (request: Request) => ({ ...(await request.json()), name: TASK.name, items_changed: [] }));
  const savedSettings = vi.fn(async (request: Request) => ({ ...DEV, ...(await request.json()) }));
  const sentBack = vi.fn(async (request: Request) => ({ ...SESSION, status: "queued", ...(await request.json()) }));
  mockApi({
    ...PROJECT_API,
    "GET /copilot/status": { installed: true, version: "x", prompts: [], default_model: "", models: [] },
    "GET /projects/acme/notes": [],
    "GET /projects/acme/agent-tasks": [TASK],
    "GET /projects/acme/activities": [],
    "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }, { path: "lib", name: "lib" }],
    "GET /projects/acme/git/branches": (request: Request) => BRANCHES[new URL(request.url).searchParams.get("path") as "api" | "lib"],
    "GET /projects/acme/dev-settings": DEV,
    "PUT /projects/acme/dev-settings": savedSettings,
    "POST /projects/acme/copilot-sessions": started,
    "GET /projects/acme/copilot-sessions": [SESSION],
    "GET /copilot-sessions/4/messages": [
      { id: 1, role: "event", content: "✅ Finita: 1 file modificati nel repository.", created_at: "2026-11-11T10:00:00Z" },
      { id: 2, role: "event", content: "🔍 Verifica fallita.\n\nStep 2 (Test): Test falliti:\nFAILED test_login", created_at: "2026-11-11T10:00:01Z" },
    ],
    "GET /copilot-sessions/4/turns": {
      total: { premium_requests: 1, ai_credits: 0.3, input_tokens: 10, output_tokens: 5, cache_read_tokens: 0, cache_write_tokens: 0,
               reasoning_tokens: 0, api_duration_ms: 0 },
      turns: [],
    },
    "PUT /projects/acme/agent-tasks/agent-task-login.md": savedTask,
    "POST /copilot-sessions/4/send-back": sentBack,
    ...extra,
  });
  return { started, savedTask, savedSettings, sentBack };
}

const renderAt = (route: string) => renderPage(<Routes>{projectRoutes()}</Routes>, { route });

describe("development checks", () => {
  it("the settings, in «Progetto» → Impostazioni, save the default scope and a command", async () => {
    const { savedSettings } = api({ "GET /projects/acme/data-settings": { visible_note_types: ["generic"], files_visible: true, due_soon_days: 3 } });
    renderAt("/projects/acme/project?tab=settings");

    fireEvent.click(await screen.findByRole("button", { name: /🧪 Verifiche dello sviluppo/ }));
    fireEvent.click(await screen.findByRole("button", { name: /⚙️ Verifiche dello sviluppo/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Prima e dopo Copilot non parte niente da solo/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("Solo i test toccati"));
    fireEvent.change(within(dialog).getByLabelText("Comando dei test di lib"), { target: { value: "./mvnw -q test" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(savedSettings).toHaveBeenCalled());
    expect(await savedSettings.mock.results[0].value).toMatchObject({ test_scope: "touched", commands: { api: "", lib: "./mvnw -q test" } });
  });

  it("a development chooses its tests and writes its Pre and Post", async () => {
    const pre = { steps: ["Branch dal main"], commands: [], automation: "" };
    const { savedTask } = api({ "GET /projects/acme/agent-tasks": [{ ...TASK, status: "todo", pre, post: { steps: [], commands: [], automation: "" } }] });
    renderAt(`/projects/acme/work?note=${TASK.name}`);

    fireEvent.click(await screen.findByText("Solo i test toccati"));
    const [, post] = screen.getAllByLabelText(/^Comandi/);
    fireEvent.change(post, { target: { value: "mvn -B test" } });
    fireEvent.click(screen.getByRole("button", { name: /Salva/ }));
    await waitFor(() => expect(savedTask).toHaveBeenCalled());
    expect(await savedTask.mock.results[0].value).toMatchObject({ tests: "touched", pre, post: { commands: ["mvn -B test"] } });
  });

  it("a development to verify is sent back to Copilot with what to fix", async () => {
    const { sentBack } = api();
    renderAt(`/projects/acme/work?note=${TASK.name}`);

    fireEvent.click(await screen.findByRole("button", { name: /Rimanda a Copilot/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByLabelText("Cosa deve sistemare"), { target: { value: "Il test del login fallisce" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Rimanda" }));
    await waitFor(() => expect(sentBack).toHaveBeenCalled());
    expect(await sentBack.mock.results[0].value).toMatchObject({ text: "Il test del login fallisce" });
  });

  it("a development opened from an activity: «← Torna all'attività»", async () => {
    api({
      "GET /projects/acme/agent-tasks": [{ ...TASK, status: "todo" }],
      "GET /projects/acme/activities": [{ name: "attivita-login.md", title: "Login", status: "in_progress", description: "", items: [],
        agent_tasks: [TASK.name], references: [] }],
    });
    renderAt(`/projects/acme/work?note=${TASK.name}&from=attivita-login.md`);

    expect(await screen.findByRole("button", { name: /Delega a Copilot/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "← Torna all'attività" }));
    expect(await screen.findByRole("tab", { name: /Lavora/ })).toBeInTheDocument();
  });
});
