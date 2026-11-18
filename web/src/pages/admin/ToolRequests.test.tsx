import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { AdminPage } from "./AdminPage";

/** Plan 20, Admin → «Richieste di tool»: the requests for Claude Code, the token and the command, dismissing one. */

afterEach(() => vi.unstubAllGlobals());

const REQUEST = (id: number, title: string, extra = {}) => ({
  id, title, objective: "Crea un tag.", criteria: ["c'è"], project_name: "acme", automation: "Rilascio", activity: "", status: "open",
  pr_url: "", reason: "", created_at: "2026-11-18T10:00:00Z", updated_at: "2026-11-18T10:00:00Z", ...extra,
});

describe("the requests of tools", () => {
  it("lists them, generates the token with the command and dismisses one with a reason", async () => {
    const token = vi.fn(() => ({ token: "segreto", url: "http://127.0.0.1:8000/api/mcp-dev/",
      command: 'claude mcp add --transport http mbare-pilot-dev http://127.0.0.1:8000/api/mcp-dev/ --header "Authorization: Bearer segreto"' }));
    const dismissed = vi.fn(async (request: Request) => ({ ...REQUEST(1, "Tool git_tag"), status: "dismissed", ...(await request.json()) }));
    mockApi({
      "GET /admin/tool-requests": {
        has_token: false, url: "http://127.0.0.1:8000/api/mcp-dev/",
        requests: [REQUEST(1, "Tool git_tag"), REQUEST(2, "Tool jira_comment", { status: "done", pr_url: "https://github.com/x/y/pull/7" })],
      },
      "POST /admin/tool-requests/token": token,
      "POST /admin/tool-requests/1/dismiss": dismissed,
    });
    renderPage(<AdminPage />, { route: "/admin?tab=tool-requests&request=1" });

    expect(await screen.findByText("Tool git_tag")).toBeInTheDocument();
    expect(screen.getByText("fatta")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PR" })).toHaveAttribute("href", "https://github.com/x/y/pull/7");
    fireEvent.click(screen.getByRole("button", { name: "Genera il token" }));
    expect(await screen.findByText(/Authorization: Bearer segreto/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Scarta" }));
    fireEvent.change(screen.getByLabelText("Perché scarti la richiesta 1"), { target: { value: "c'è già" } });
    fireEvent.click(screen.getByRole("button", { name: "Scarta" }));
    await waitFor(() => expect(dismissed).toHaveBeenCalled());
    expect(await dismissed.mock.results[0].value).toMatchObject({ reason: "c'è già" });
  });
});
