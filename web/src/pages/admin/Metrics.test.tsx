import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { Metrics } from "./Metrics";

afterEach(() => vi.unstubAllGlobals());

const METRICS = {
  days: 30, project_name: null,
  agents: [{ name: "chatbot/Segretario", calls: 12, errors: 1, input_tokens: 4000, output_tokens: 600, cost_eur: 0.0123,
             latency_avg_ms: 1500, latency_p95_ms: 4200, models: ["gemini-3.1-flash-lite-preview"] }],
  copilot: [{ model: "gpt-5", turns: 4, usage: { premium_requests: 4, ai_credits: 1.5, input_tokens: 9000, output_tokens: 300, cache_read_tokens: 0,
                                                 cache_write_tokens: 0, reasoning_tokens: 0, api_duration_ms: 0 } }],
  wip: { runs: 5, applied: 3, dismissed: 1, open: 1, proposed: 14, accepted: 7, corrected: 2, discarded: 3, skipped: 0, acceptance_rate: 0.583 },
};
const REPORT = { name: "rag-20261110-120000", kind: "rag", created_at: "2026-11-10T12:00:00Z" };

describe("Metriche", () => {
  it("shows cost and latency by who, Copilot apart and the WIP acceptance, by period and project", async () => {
    const asked: string[] = [];
    mockApi({
      "GET /observability/metrics": (request: Request) => { asked.push(new URL(request.url).search); return METRICS; },
      "GET /projects": [{ name: "acme" }],
      "GET /observability/evaluations": { runs: [], reports: [] },
      "GET /models": [],
    });
    renderPage(<Metrics />);

    expect(await screen.findByText("chatbot/Segretario")).toBeInTheDocument();
    expect(screen.getByText("4,2 s")).toBeInTheDocument(); // p95
    expect(screen.getByText(/1,50 crediti/)).toBeInTheDocument();
    expect(screen.getByText("58%")).toBeInTheDocument();
    expect(screen.getByText("Nessun report ancora.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Tutto" }));
    await waitFor(() => expect(asked.at(-1)).toBe(""));
    expect(asked[0]).toBe("?days=30");
  });

  it("launches the evaluations and opens a report", async () => {
    const launched = vi.fn(async (request: Request) => ({ id: 1, status: "queued", ...(await request.json()) }));
    mockApi({
      "GET /observability/metrics": { ...METRICS, agents: [], copilot: [], wip: { ...METRICS.wip, runs: 0 } },
      "GET /projects": [],
      "GET /observability/evaluations": { runs: [{ id: 2, kind: "wip", status: "failed", error: "quota finita", created_at: "2026-11-10T11:00:00Z" }], reports: [REPORT] },
      "GET /models": [{ provider: "openrouter", model: "google/gemini-3.1-flash-lite-preview", active: true }, { provider: "mock", model: "echo", active: true }],
      "POST /observability/evaluations": launched,
      "GET /observability/evaluations/reports/rag-20261110-120000": () => new Response("# Valutazione della ricerca\n\n| a | b |\n|---|---|\n| 1 | 2 |"),
    });
    renderPage(<Metrics />);

    expect(await screen.findByText("Nessuna chiamata nel periodo.")).toBeInTheDocument();
    expect(await screen.findByText(/quota finita/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Valuta Elabora WIP" }));
    await waitFor(() => expect(launched).toHaveBeenCalledTimes(1));
    expect(await launched.mock.results[0].value).toMatchObject({ kind: "wip", models: ["openrouter/google/gemini-3.1-flash-lite-preview"] });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Valuta il RAG" }));
    await waitFor(() => expect(launched).toHaveBeenCalledTimes(2));
    expect(await launched.mock.results[1].value).toMatchObject({ kind: "rag", embedders: ["hashing", "openrouter/openai/text-embedding-3-small"] });

    fireEvent.click(screen.getByRole("button", { name: REPORT.name }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Valutazione della ricerca")).toBeInTheDocument();
    expect(within(dialog).getByRole("table")).toBeInTheDocument();
  });
});
