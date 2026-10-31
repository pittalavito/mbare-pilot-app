import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CopilotSession } from "../../api/copilot";
import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "../data/DataTab";
import { CopilotTab } from "./CopilotTab";

afterEach(() => vi.unstubAllGlobals());

const session = (patch: Partial<CopilotSession> = {}): CopilotSession => ({
  id: 4, project_name: "acme", task_note: "agent-task-fix-porto.md", repository: "api", repositories: ["api"], prompt: "", model: "", status: "planning", planning_turn: null,
  cancel_requested: false,
  head_before: null, head_after: null, heads_before: null, heads_after: null, head_moved: false, moved_repositories: [], changed_files: [],
  outside_files: [], premium_requests: 1, error: null,
  created_at: "2026-10-26T10:00:00Z", updated_at: "2026-10-26T10:00:00Z", started_at: null, finished_at: null, ...patch,
});
const MESSAGES = [
  { id: 1, role: "user", content: "Ti affido il task…", created_at: "2026-10-26T10:00:00Z" },
  { id: 2, role: "copilot", content: "**Domanda**: ValueError o ZeroDivisionError?", created_at: "2026-10-26T10:00:10Z" },
];

const renderTab = (route = "/projects/acme/copilot") =>
  renderPage(
    <Routes>
      <Route path="/projects/:project/copilot" element={<CopilotTab />} />
      <Route path="/projects/:project/data" element={<DataTab />} />
    </Routes>,
    { route },
  );

describe("CopilotTab", () => {
  it("shows the planning chat, answers Copilot and gives the ok", async () => {
    const sent = vi.fn(async (request: Request) => ({ ...session({ planning_turn: "queued" }), ...(await request.json()) }));
    const approved = vi.fn(() => session({ status: "queued" }));
    mockApi({
      "GET /copilot/status": { installed: true, version: "GitHub Copilot CLI 1.0.103." },
      "GET /projects/acme/copilot-sessions": [session()],
      "GET /copilot-sessions/4/messages": MESSAGES,
      "GET /copilot-sessions/4/turns": {
        total: { premium_requests: 2, ai_credits: 0.68, input_tokens: 53472, output_tokens: 194, cache_read_tokens: 0, cache_write_tokens: 0,
                 reasoning_tokens: 0, api_duration_ms: 0 },
        turns: [],
      },
      "POST /copilot-sessions/4/messages": sent,
      "POST /copilot-sessions/4/approve": approved,
    });
    renderTab();

    expect(await screen.findByText("Domanda")).toHaveProperty("tagName", "STRONG"); // Copilot's markdown
    expect(await screen.findByText(/0,68 crediti AI · 2 richieste premium · token 53.472 in \/ 194 out/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Rispondi a Copilot/), { target: { value: "ValueError" } });
    fireEvent.keyDown(screen.getByPlaceholderText(/Rispondi a Copilot/), { key: "Enter" });
    await waitFor(() => expect(sent).toHaveBeenCalled());
    expect(await sent.mock.results[0].value).toMatchObject({ text: "ValueError" });

    fireEvent.click(screen.getByRole("button", { name: /Ok, parti/ }));
    await waitFor(() => expect(approved).toHaveBeenCalled());
  });

  it("while Copilot executes the chat waits and the execution can be cancelled; at the end the changed files show", async () => {
    const cancelled = vi.fn(() => session({ status: "running", cancel_requested: true }));
    mockApi({
      "GET /copilot/status": { installed: true, version: "x" },
      "GET /projects/acme/copilot-sessions": [
        session({ status: "running" }),
        session({
          id: 5, task_note: "agent-task-altro.md", status: "done", repository: "", repositories: ["api", "web"], changed_files: ["api/calc.py"],
          head_moved: true, moved_repositories: ["web"], heads_before: { api: "cccccccc1", web: "aaaaaaaa1" },
          heads_after: { api: "cccccccc1", web: "bbbbbbbb2" }, outside_files: ["lib/x.py"],
        }),
      ],
      "GET /copilot-sessions/4/messages": MESSAGES,
      "GET /copilot-sessions/5/messages": [],
      "POST /copilot-sessions/4/cancel": cancelled,
    });
    renderTab("/projects/acme/copilot?session=4");

    expect(await screen.findByPlaceholderText(/Copilot sta eseguendo/)).toBeDisabled();
    expect(screen.getByText("Copilot sta lavorando sui file…")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Annulla/ }));
    await waitFor(() => expect(cancelled).toHaveBeenCalled());

    fireEvent.click(screen.getByText("altro"));
    expect(await screen.findByText("api/calc.py")).toBeInTheDocument();
    expect(screen.getByText(/L'HEAD è cambiato/)).toBeInTheDocument();
    expect(screen.getByText(/web: aaaaaaaa → bbbbbbbb/)).toBeInTheDocument(); // only the repository that moved
    expect(screen.getByText("Cambiati 1 file in repository non scelti")).toBeInTheDocument();
    expect(screen.getByText("lib/x.py")).toBeInTheDocument();
    expect(screen.getAllByText("api, web").length).toBeGreaterThan(0);
  });

  it("while Copilot writes the chat waits, follows the worker's answer and warns when no worker is on", async () => {
    let answered = false;
    mockApi({
      "GET /copilot/status": { installed: true, version: "x" },
      "GET /admin/worker": { workers: [] },
      "GET /projects/acme/copilot-sessions": () => [session({ planning_turn: answered ? null : "queued" })],
      "GET /copilot-sessions/4/messages": () => {
        if (answered) return MESSAGES;
        answered = true; // the worker answers before the next poll
        return MESSAGES.slice(0, 1);
      },
    });
    renderTab();

    expect(await screen.findByText("Copilot sta scrivendo…")).toBeInTheDocument();
    expect(screen.getAllByText("Copilot scrive…").length).toBeGreaterThan(0); // the badges
    expect(screen.getByPlaceholderText(/Copilot sta scrivendo: aspetta/)).toBeDisabled();
    expect(screen.getByRole("button", { name: /Ok, parti/ })).toBeDisabled();
    expect(await screen.findByText(/Nessun worker attivo: Copilot risponde solo quando il worker è acceso/)).toBeInTheDocument();

    expect(await screen.findByText("Domanda", {}, { timeout: 5_000 })).toBeInTheDocument(); // polled every 3 seconds
    await waitFor(() => expect(screen.queryByText("Copilot sta scrivendo…")).not.toBeInTheDocument(), { timeout: 5_000 });
    expect(screen.getByPlaceholderText(/Rispondi a Copilot/)).toBeEnabled();
    expect(screen.getByRole("button", { name: /Ok, parti/ })).toBeEnabled();
  }, 15_000);

  it("stops Copilot's pending answer", async () => {
    const cancelled = vi.fn(() => session());
    mockApi({
      "GET /copilot/status": { installed: true, version: "x" },
      "GET /admin/worker": { workers: [{ worker_id: "h-1", host: "h", pid: 1, busy_run_id: null, busy_copilot_session_ids: [4] }] },
      "GET /projects/acme/copilot-sessions": [session({ planning_turn: "running" })],
      "GET /copilot-sessions/4/messages": MESSAGES.slice(0, 1),
      "POST /copilot-sessions/4/cancel": cancelled,
    });
    renderTab();

    expect(await screen.findByText("Copilot sta scrivendo…")).toBeInTheDocument();
    expect(screen.queryByText(/Nessun worker attivo/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Elimina" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Annulla/ }));
    await waitFor(() => expect(cancelled).toHaveBeenCalled());
  });

  it("marks the sessions whose agent task was deleted", async () => {
    const TASK = { name: "agent-task-fix-porto.md", title: "Fix porto", status: "todo", objective: "", context: "", criteria: [], constraints: "" };
    mockApi({
      "GET /copilot/status": { installed: true, version: "x" },
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/copilot-sessions": [session(), session({ id: 5, task_note: "agent-task-sparito.md" })],
      "GET /copilot-sessions/4/messages": MESSAGES,
    });
    renderTab();

    expect(await screen.findByText("task eliminato")).toBeInTheDocument();
    expect(screen.getAllByText("task eliminato")).toHaveLength(1); // only «sparito»
  });

  it("delegates a task from its form and opens its chat", async () => {
    const started = vi.fn(async (request: Request) => ({ ...session({ id: 9 }), ...(await request.json()) }));
    const TASK = { name: "agent-task-fix-porto.md", title: "Fix porto", status: "todo", objective: "", context: "", criteria: [], constraints: "" };
    mockApi({
      "GET /copilot/status": {
        installed: true, version: "x", prompts: ["bug"], default_model: "",
        models: [{
          name: "claude-haiku-5.5", note: "per i task piccoli", price: { input: 0.1, cached_input: 0.01, cache_write: 0.125, output: 0.5 },
          long_context_above: 100000, long_context_price: { input: 0.5, cached_input: 0.05, cache_write: 0.625, output: 2.5 },
          turns: 3, average_ai_credits: 0.34,
        }],
      },
      "GET /projects/acme/notes": [],
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }, { path: "web", name: "web" }],
      "POST /projects/acme/copilot-sessions": started,
      "GET /projects/acme/copilot-sessions": () => (started.mock.calls.length ? [session({ id: 9 })] : []),
      "GET /copilot-sessions/9/messages": MESSAGES,
    });
    renderTab("/projects/acme/data");

    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Delega a Copilot/ }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Delega" })).toBeEnabled()); // all the repositories are chosen
    expect(within(dialog).getByDisplayValue("Predefinito (plan_prompt)")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByDisplayValue("Predefinito (di Copilot)"));
    fireEvent.click(await screen.findByRole("option", { name: "claude-haiku-5.5 · $0,10 / $0,50" }));
    expect(await within(dialog).findByText("per i task piccoli")).toBeInTheDocument();
    expect(within(dialog).getByText(/Finora: 0,34 crediti AI per turno in media \(3 turni/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Oltre 100.000 token di input/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    await waitFor(() => expect(started).toHaveBeenCalled());
    expect(await started.mock.results[0].value).toMatchObject({ task_note: "agent-task-fix-porto.md", repositories: ["api", "web"], prompt: "", model: "claude-haiku-5.5" });
    expect(await screen.findByText("Domanda")).toBeInTheDocument(); // now on the Copilot tab, its chat open
  });
});
