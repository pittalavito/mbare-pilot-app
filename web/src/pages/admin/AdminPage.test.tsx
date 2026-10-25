import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { LibraryPage } from "../library/LibraryPage";
import { AdminPage } from "./AdminPage";

afterEach(() => vi.unstubAllGlobals());

const tokens = (input: number, output: number, cost: number) => ({ input_tokens: input, output_tokens: output, cost_eur: cost });
const RUN = {
  run_id: "abcdef1234567890", project_name: "acme", origin: "chatbot", config_name: "Navi bot", role_name: "chatbot", prompt_version: 3,
  model: "mock/echo", ok: false, error: "tool fallito", latency_ms: 812.4, agent_tokens: tokens(100, 20, 0.001),
  tool_tokens: tokens(0, 0, 0), total_tokens: tokens(100, 20, 0.001), tool_names: ["git_status"], created_at: "2026-10-25T10:00:00Z",
};
const MODELS = [
  { provider: "mock", model: "mock/echo", input_per_1m: 0, output_per_1m: 0, active: true, in_use: true },
  { provider: "openai", model: "gpt-4o", input_per_1m: 2.3, output_per_1m: 9.2, active: true, in_use: false },
];

describe("AdminPage", () => {
  it("shows the runs and the trace of the one clicked", async () => {
    mockApi({
      "GET /admin/config": { settings: {}, redis_dashboard_port: 8081, postgres_dashboard_port: 8082 },
      "GET /observability/runs": [RUN],
      "GET /observability/tool-calls": [],
      "GET /observability/runs/abcdef1234567890/trace": { steps: ["pensa", "chiama git_status"] },
    });
    renderPage(<AdminPage />, { route: "/admin?tab=observability" });

    fireEvent.click(await screen.findByText("abcdef12…"));

    expect(await screen.findByText("tool fallito")).toBeInTheDocument();
    expect(await screen.findByText(/chiama git_status/)).toBeInTheDocument();
  });

  it("saves the catalog without the removed model; one in use cannot be removed", async () => {
    const saved = vi.fn(async (request: Request) => request.json());
    mockApi({ "GET /models": MODELS, "PUT /models": saved });
    renderPage(<AdminPage />, { route: "/admin?tab=models" });

    const remove = await screen.findAllByRole("button", { name: "🗑" });
    expect(remove[0]).toBeDisabled(); // mock/echo is in use
    expect(screen.getByRole("button", { name: "Salva" })).toBeDisabled();
    fireEvent.click(remove[1]);
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toEqual([MODELS[0]]);
  });
});

describe("LibraryPage", () => {
  it("lists the tool catalog", async () => {
    mockApi({
      "GET /agents": [],
      "GET /tools": [
        { name: "git_status", description: "Stato del repo", available: true, chatbot_only: false },
        { name: "run_automation", description: "Lancia un'automation", available: true, chatbot_only: true },
      ],
    });
    renderPage(<LibraryPage />, { route: "/library?tab=tools" });

    expect(await screen.findByText("run_automation")).toBeInTheDocument();
    expect(screen.getByText("💬")).toBeInTheDocument();
  });
});
