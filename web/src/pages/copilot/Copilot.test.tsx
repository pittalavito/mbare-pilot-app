import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CopilotSession } from "../../api/copilot";
import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";

/** Copilot without its tab (plan 13b): delegated from the task's form, its chat
 * in the agent panel of the task (questions during the execution, cancel, the
 * files changed). */

afterEach(() => vi.unstubAllGlobals());

const TASK = { name: "agent-task-fix-porto.md", title: "Fix porto", status: "todo", type: "development", objective: "", context: "", criteria: [],
  constraints: "", references: [], tests: null };
const session = (patch: Partial<CopilotSession> = {}): CopilotSession => ({
  id: 4, project_name: "acme", task_note: TASK.name, repository: "api", prompt: "", model: "", status: "planning", cancel_requested: false,
  head_before: null, head_after: null, head_moved: false, changed_files: [], premium_requests: 1, error: null,
  created_at: "2026-11-13T10:00:00Z", updated_at: "2026-11-13T10:00:00Z", started_at: null, finished_at: null, ...patch,
});
const TURNS = {
  total: { premium_requests: 1, ai_credits: 0.3, input_tokens: 10, output_tokens: 5, cache_read_tokens: 0, cache_write_tokens: 0, reasoning_tokens: 0,
           api_duration_ms: 0 },
  turns: [],
};
const MESSAGES = [
  { id: 1, role: "user", content: "Ti affido il task…", created_at: "2026-11-13T10:00:00Z" },
  { id: 2, role: "copilot", content: "**Domanda**: ValueError o ZeroDivisionError?", created_at: "2026-11-13T10:00:10Z" },
];

function Where() {
  const location = useLocation();
  return <div data-testid="where">{location.pathname + location.search}</div>;
}

const renderAt = (route: string) =>
  renderPage(<><Routes>{projectRoutes()}</Routes><Routes><Route path="*" element={<Where />} /></Routes></>, { route });

function api(extra: Record<string, unknown> = {}) {
  mockApi({
    ...PROJECT_API,
    "GET /projects/acme/agent-tasks": [{ ...TASK, status: "in_progress" }],
    "GET /copilot/status": { installed: true, version: "x", prompts: [], default_model: "", models: [] },
    "GET /copilot-sessions/4/messages": MESSAGES,
    "GET /copilot-sessions/5/messages": [],
    "GET /copilot-sessions/4/turns": TURNS,
    "GET /copilot-sessions/5/turns": TURNS,
    ...extra,
  });
}

describe("Copilot", () => {
  it("is delegated from the task's form, which then shows its chat in the panel", async () => {
    const started = vi.fn(async (request: Request) => ({ ...session({ id: 9 }), ...(await request.json()) }));
    api({
      "GET /copilot/status": {
        installed: true, version: "x", prompts: ["bug"], default_model: "",
        models: [{ name: "claude-haiku-5.5", note: "per i task piccoli", price: { input: 0.1, cached_input: 0.01, cache_write: 0.125, output: 0.5 },
                   long_context_above: null, long_context_price: null, turns: 3, average_ai_credits: 0.34 }],
      },
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }],
      "POST /projects/acme/copilot-sessions": started,
      "GET /projects/acme/copilot-sessions": () => (started.mock.calls.length ? [session({ id: 9 })] : []),
      "GET /copilot-sessions/9/messages": MESSAGES,
      "GET /copilot-sessions/9/turns": TURNS,
    });
    renderAt(`/projects/acme/work?note=${TASK.name}`);

    fireEvent.click(await screen.findByRole("button", { name: /Delega a Copilot/ }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Delega" })).toBeEnabled()); // the only repository is chosen
    fireEvent.click(within(dialog).getByDisplayValue("Predefinito (di Copilot)"));
    fireEvent.click(await screen.findByRole("option", { name: "claude-haiku-5.5 · $0,10 / $0,50" }));
    expect(await within(dialog).findByText("per i task piccoli")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    await waitFor(() => expect(started).toHaveBeenCalled());
    expect(await started.mock.results[0].value).toMatchObject({ task_note: TASK.name, repository: "api", model: "claude-haiku-5.5" });
    expect(await screen.findByText("Domanda")).toBeInTheDocument(); // the panel shows Copilot's chat
    expect(screen.getByTestId("where")).toHaveTextContent(`/projects/acme/work?note=${TASK.name}`);
  });

  it("proposes the prompt of the task's type", async () => {
    api({
      "GET /copilot/status": { installed: true, version: "x", prompts: ["analisi"], type_prompts: { analysis: "analisi" }, default_model: "", models: [] },
      "GET /projects/acme/agent-tasks": [{ ...TASK, type: "analysis" }],
      "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }],
    });
    renderAt(`/projects/acme/work?note=${TASK.name}`);

    fireEvent.click(await screen.findByRole("button", { name: /Delega a Copilot/ }));
    expect(await within(await screen.findByRole("dialog")).findByDisplayValue("Predefinito del tipo (analisi)")).toBeInTheDocument();
  });

  it("during an execution Copilot's question unlocks the box, which answers it", async () => {
    const answered = vi.fn(async (request: Request) => ({ ...session({ status: "running" }), ...(await request.json()) }));
    api({
      "GET /projects/acme/copilot-sessions": [session({ status: "running" })],
      "GET /copilot-sessions/4/messages": [
        ...MESSAGES,
        { id: 3, role: "event", content: "▶️ Esecuzione partita", created_at: "2026-11-13T10:01:00Z" },
        { id: 4, role: "question", content: "Che nome uso per il file?", created_at: "2026-11-13T10:02:00Z" },
      ],
      "POST /copilot-sessions/4/answer": answered,
    });
    renderAt(`/projects/acme/work?note=${TASK.name}`);

    expect(await screen.findByText("Che nome uso per il file?")).toBeInTheDocument();
    const box = screen.getByPlaceholderText(/Rispondi alla domanda di Copilot/);
    fireEvent.change(box, { target: { value: "calcoli.py" } });
    fireEvent.click(screen.getByRole("button", { name: "Rispondi" }));
    await waitFor(() => expect(answered).toHaveBeenCalled());
    expect(await answered.mock.results[0].value).toMatchObject({ text: "calcoli.py" });
  });

  it("while it executes the chat waits and it can be cancelled; an older session shows its changed files", async () => {
    const cancelled = vi.fn(() => session({ status: "running", cancel_requested: true }));
    api({
      "GET /projects/acme/copilot-sessions": [
        session({ status: "running" }),
        session({ id: 5, status: "done", changed_files: ["calc.py"], head_moved: true, head_before: "aaaaaaaa1", head_after: "bbbbbbbb2" }),
      ],
      "POST /copilot-sessions/4/cancel": cancelled,
    });
    renderAt(`/projects/acme/work?note=${TASK.name}`);

    expect(await screen.findByPlaceholderText(/Copilot sta eseguendo/)).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Annulla/ }));
    await waitFor(() => expect(cancelled).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("textbox", { name: "Sessione Copilot" }));
    fireEvent.click(await screen.findByRole("option", { name: /Sessione 5/ }));
    expect(await screen.findByText("calc.py")).toBeInTheDocument();
    expect(screen.getByText(/L'HEAD è cambiato/)).toBeInTheDocument();
  });
});
