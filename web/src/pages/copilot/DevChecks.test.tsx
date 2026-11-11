import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "../data/DataTab";
import { CopilotTab } from "./CopilotTab";

/** Blocco 09: «Prepara sviluppo» in the delegation, the tests' settings, the
 * task's choice of tests and the failed verification ready to send back. */

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
  test_scope: "all", prepare_automation: true, verify_automation: true,
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

const renderAt = (route: string) =>
  renderPage(
    <Routes>
      <Route path="/projects/:project/copilot" element={<CopilotTab />} />
      <Route path="/projects/:project/data" element={<DataTab />} />
    </Routes>,
    { route },
  );

describe("development checks", () => {
  it("the delegation prepares the task's repository and a library on a new branch", async () => {
    const { started } = api();
    renderAt("/projects/acme/copilot");

    fireEvent.click(await screen.findByRole("button", { name: /Delega un task/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByPlaceholderText("Scegli il task"));
    fireEvent.click(await screen.findByRole("option", { name: "Login" }));
    fireEvent.click(within(dialog).getByPlaceholderText("Scegli il repository"));
    fireEvent.click(await screen.findByRole("option", { name: "api" }));

    expect(await within(dialog).findByDisplayValue("develop")).toBeInTheDocument(); // the current branch
    fireEvent.click(within(dialog).getByRole("button", { name: /Un altro repository/ }));
    const branch = await within(dialog).findByLabelText("Branch di lib");
    await waitFor(() => expect(branch).toHaveValue("main"));
    fireEvent.change(branch, { target: { value: "feature/login" } });
    expect(await within(dialog).findByText(/non esiste: scegli da quale branch crearlo/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByLabelText("Base di lib"));
    fireEvent.click(await screen.findByRole("option", { name: "release" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    await waitFor(() => expect(started).toHaveBeenCalled());
    expect(await started.mock.results[0].value).toMatchObject({
      prepare: [{ repository: "api", branch: "develop", base: "" }, { repository: "lib", branch: "feature/login", base: "release" }],
    });
  });

  it("without preparing, the delegation sends no repositories and a failed preparation is shown", async () => {
    const failing = vi.fn(() => new Response(JSON.stringify({ detail: "Preparazione non riuscita, Copilot non è partito." }), { status: 409 }));
    api({ "POST /projects/acme/copilot-sessions": failing });
    renderAt("/projects/acme/copilot");

    fireEvent.click(await screen.findByRole("button", { name: /Delega un task/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByPlaceholderText("Scegli il task"));
    fireEvent.click(await screen.findByRole("option", { name: "Login" }));
    fireEvent.click(within(dialog).getByPlaceholderText("Scegli il repository"));
    fireEvent.click(await screen.findByRole("option", { name: "api" }));
    fireEvent.click(await within(dialog).findByLabelText(/Prepara i repository/));
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    expect(await within(dialog).findByText("Preparazione non riuscita, Copilot non è partito.")).toBeInTheDocument();
    expect(await (failing.mock.calls[0] as unknown as [Request])[0].json()).toMatchObject({ prepare: [] });
  });

  it("the settings save the default scope and a command", async () => {
    const { savedSettings } = api();
    renderAt("/projects/acme/copilot");

    fireEvent.click(await screen.findByRole("button", { name: /Verifiche dello sviluppo/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Prepara sviluppo: attiva")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("Solo i test toccati"));
    fireEvent.change(within(dialog).getByLabelText("Comando dei test di lib"), { target: { value: "./mvnw -q test" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(savedSettings).toHaveBeenCalled());
    expect(await savedSettings.mock.results[0].value).toMatchObject({ test_scope: "touched", commands: { api: "", lib: "./mvnw -q test" } });
  });

  it("a task chooses its tests and its failed verification is ready to send back", async () => {
    const { savedTask, sentBack } = api();
    renderAt(`/projects/acme/data?note=${TASK.name}`);

    fireEvent.click(await screen.findByText("Solo i test toccati"));
    fireEvent.click(screen.getByRole("button", { name: /Salva/ }));
    await waitFor(() => expect(savedTask).toHaveBeenCalled());
    expect(await savedTask.mock.results[0].value).toMatchObject({ tests: "touched" });

    fireEvent.click(screen.getByRole("button", { name: /Rimanda a Copilot/ }));
    const dialog = await screen.findByRole("dialog");
    const message = await within(dialog).findByLabelText("Cosa deve sistemare");
    await waitFor(() => expect((message as HTMLTextAreaElement).value).toContain("FAILED test_login"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Rimanda" }));
    await waitFor(() => expect(sentBack).toHaveBeenCalled());
  });
});
