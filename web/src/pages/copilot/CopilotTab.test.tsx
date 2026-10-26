import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CopilotSession } from "../../api/copilot";
import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "../data/DataTab";
import { CopilotTab } from "./CopilotTab";

afterEach(() => vi.unstubAllGlobals());

const session = (patch: Partial<CopilotSession> = {}): CopilotSession => ({
  id: 4, project_name: "acme", task_note: "agent-task-fix-porto.md", repository: "api", status: "planning", cancel_requested: false,
  head_before: null, head_after: null, head_moved: false, changed_files: [], premium_requests: 1, error: null,
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
    const sent = vi.fn(async (request: Request) => ({ ...session(), ...(await request.json()) }));
    const approved = vi.fn(() => session({ status: "queued" }));
    mockApi({
      "GET /copilot/status": { installed: true, version: "GitHub Copilot CLI 1.0.103." },
      "GET /projects/acme/copilot-sessions": [session()],
      "GET /copilot-sessions/4/messages": MESSAGES,
      "POST /copilot-sessions/4/messages": sent,
      "POST /copilot-sessions/4/approve": approved,
    });
    renderTab();

    expect(await screen.findByText("Domanda")).toHaveProperty("tagName", "STRONG"); // Copilot's markdown
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
        session({ id: 5, task_note: "agent-task-altro.md", status: "done", changed_files: ["calc.py"], head_moved: true, head_before: "aaaaaaaa1", head_after: "bbbbbbbb2" }),
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
    expect(await screen.findByText("calc.py")).toBeInTheDocument();
    expect(screen.getByText(/L'HEAD è cambiato/)).toBeInTheDocument();
  });

  it("delegates a task from its form and opens its chat", async () => {
    const started = vi.fn(async (request: Request) => ({ ...session({ id: 9 }), ...(await request.json()) }));
    const TASK = { name: "agent-task-fix-porto.md", title: "Fix porto", status: "todo", objective: "", context: "", criteria: [], constraints: "" };
    mockApi({
      "GET /copilot/status": { installed: true, version: "x" },
      "GET /projects/acme/notes": [],
      "GET /projects/acme/agent-tasks": [TASK],
      "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }],
      "POST /projects/acme/copilot-sessions": started,
      "GET /projects/acme/copilot-sessions": () => (started.mock.calls.length ? [session({ id: 9 })] : []),
      "GET /copilot-sessions/9/messages": MESSAGES,
    });
    renderTab("/projects/acme/data");

    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Delega a Copilot/ }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Delega" })).toBeEnabled()); // the only repository is chosen
    fireEvent.click(within(dialog).getByRole("button", { name: "Delega" }));

    await waitFor(() => expect(started).toHaveBeenCalled());
    expect(await started.mock.results[0].value).toMatchObject({ task_note: "agent-task-fix-porto.md", repository: "api" });
    expect(await screen.findByText("Domanda")).toBeInTheDocument(); // now on the Copilot tab, its chat open
  });
});
