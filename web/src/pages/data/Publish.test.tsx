import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "./DataTab";
import { diffLines } from "./PublishModal";

/** Blocco 10: «Pubblica su Confluence/Jira» from the task and from its draft. */

afterEach(() => vi.unstubAllGlobals());

const task = (type: string, references: string[] = ["bozza-guida.md"]) => ({
  name: "agent-task-guida.md", title: "Guida", status: "in_progress", type, objective: "", context: "", criteria: [], constraints: "",
  references, tests: null,
});

function api(type: string, preview: Record<string, unknown>, references?: string[]) {
  const published = vi.fn(async (request: Request) => ({ kind: type, mode: preview.mode, url: "https://acme.atlassian.net/x", reference: "r.md",
                                                          ...(await request.json()) }));
  mockApi({
    "GET /projects/acme/notes": [{ name: "bozza-guida.md", size: 10, modified_at: "2026-11-11T10:00:00Z", note_type: "generic" }],
    "GET /projects/acme/notes/bozza-guida.md": { name: "bozza-guida.md", content: "# Bozza: Guida\n\n## Contesto\nTesto" },
    "GET /projects/acme/agent-tasks": [task(type, references)],
    "GET /projects/acme/activities": [],
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/agent-tasks/agent-task-guida.md/publish": { kind: type, draft: "bozza-guida.md", title: "Guida", body: "## Contesto\nTesto nuovo",
                                                                    unmasked: [], reference: null, target_title: "", target_body: "", target_url: "",
                                                                    space_key: "", project_key: "", ...preview },
    "GET /projects/acme/atlassian/confluence/pages": [{ id: "55", title: "Architettura", url: "u", space_id: "9", body: "" }],
    "GET /projects/acme/atlassian/jira/issue-types": ["Story", "Bug"],
    "POST /projects/acme/agent-tasks/agent-task-guida.md/publish": published,
  });
  return { published };
}

const renderData = (route: string) =>
  renderPage(<Routes><Route path="/projects/:project/data" element={<DataTab />} /></Routes>, { route });

describe("publish a draft", () => {
  it("a new Confluence page, under a parent, from the task", async () => {
    const { published } = api("confluence", { mode: "create", space_key: "DOC", unmasked: ["REPO_1 → login-api"] });
    renderData("/projects/acme/data?note=agent-task-guida.md");

    fireEvent.click(await screen.findByRole("button", { name: /Pubblica su Confluence/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Una pagina nuova/)).toBeInTheDocument();
    expect(within(dialog).getByText(/REPO_1 → login-api/)).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("DOC")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByPlaceholderText(/In cima allo spazio|Carico/));
    fireEvent.click(await screen.findByRole("option", { name: "Architettura" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Pubblica" }));

    await waitFor(() => expect(published).toHaveBeenCalled());
    expect(await published.mock.results[0].value).toMatchObject({ space_key: "DOC", parent_id: "55", project_key: "", issue_type: "" });
  });

  it("a new Jira issue needs its type; from the draft note", async () => {
    const { published } = api("jira", { mode: "create", project_key: "NAV" });
    renderData("/projects/acme/data?note=bozza-guida.md");

    fireEvent.click(await screen.findByRole("button", { name: /Pubblica su Jira/ }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByDisplayValue("NAV");
    expect(within(dialog).getByRole("button", { name: "Pubblica" })).toBeDisabled();
    fireEvent.click(within(dialog).getByPlaceholderText(/Scegli|Carico/));
    fireEvent.click(await screen.findByRole("option", { name: "Story" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Pubblica" }));

    await waitFor(() => expect(published).toHaveBeenCalled());
    expect(await published.mock.results[0].value).toMatchObject({ project_key: "NAV", issue_type: "Story" });
  });

  it("an update shows the comparison with the current text", async () => {
    api("jira", { mode: "update", reference: "context-reference-nav-7.md", target_title: "NAV-7 · Login lento", target_body: "## Contesto\nTesto vecchio",
                  target_url: "https://acme.atlassian.net/browse/NAV-7" });
    renderData("/projects/acme/data?note=agent-task-guida.md");

    fireEvent.click(await screen.findByRole("button", { name: /Pubblica su Jira/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/cambia solo la descrizione/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("tab", { name: /Confronto/ }));
    expect(await within(dialog).findByText("- Testo vecchio")).toBeInTheDocument();
    expect(within(dialog).getByText("+ Testo nuovo")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Pubblica" })).toBeEnabled();
  });

  it("no button without a draft or for another type", async () => {
    api("confluence", { mode: "create" }, []);
    renderData("/projects/acme/data?note=agent-task-guida.md");
    expect(await screen.findByDisplayValue("Guida")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pubblica su/ })).not.toBeInTheDocument();
  });

  it("diffs lines", () => {
    expect(diffLines("a\nb\nc", "a\nx\nc")).toEqual([
      { kind: "same", text: "a" }, { kind: "removed", text: "b" }, { kind: "added", text: "x" }, { kind: "same", text: "c" },
    ]);
    expect(diffLines("", "y").map((line) => line.kind)).toEqual(["removed", "added"]);
  });
});
