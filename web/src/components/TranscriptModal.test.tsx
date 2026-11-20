import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../test/render";
import { TranscriptModal } from "./TranscriptModal";

afterEach(() => vi.unstubAllGlobals());

const view = (who: string, repo: string) => ({
  system_prompt: "Sei il segretario.",
  history: [{ role: "user", content: `ciao, sono ${who}` }],
  input: `${who} chiede di ${repo}`,
  tool_calls: [{ name: "git_status", arguments: `{\n  "repository": "${repo}"\n}`, result: `Repository ${repo}: pulito`, error: null }],
  output: `Ho controllato **${repo}**.`,
});

describe("TranscriptModal", () => {
  it("shows every part, masked or in clear", async () => {
    mockApi({
      "GET /observability/runs/r1/transcript": {
        run_id: "r1", project_name: "acme", masked: view("PERSONA_1", "REPO_1"), clear: view("Mario Rossi", "project-be"), aliases: ["PERSONA_1", "REPO_1"],
      },
    });
    renderPage(<TranscriptModal runId="r1" opened onClose={() => undefined} />);

    expect(await screen.findByText(/chiede di/)).toBeInTheDocument();
    expect(screen.getAllByText("REPO_1").length).toBeGreaterThan(0); // highlighted
    fireEvent.click(screen.getByText(/Chiamate ai tool \(1\)/));
    expect(await screen.findByText("1. git_status")).toBeInTheDocument();

    fireEvent.click(screen.getByText("👁 In chiaro"));
    expect(await screen.findByText(/Mario Rossi chiede di project-be/)).toBeInTheDocument();
    expect(screen.queryByText("REPO_1")).not.toBeInTheDocument();
  });

  it("says when the run has no transcript", async () => {
    mockApi({ "GET /observability/runs/r2/transcript": () => new Response(JSON.stringify({ detail: "Questa esecuzione non ha la trascrizione" }), { status: 404 }) });
    renderPage(<TranscriptModal runId="r2" opened onClose={() => undefined} />);
    expect(await screen.findByText(/non ha la trascrizione/)).toBeInTheDocument();
  });
});
