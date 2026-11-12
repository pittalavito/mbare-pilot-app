import { fireEvent, screen } from "@testing-library/react";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";

/** Plan 13a: the zones «Lavoro» and «Progetto», an agent task opened inside its
 * activity, and the links of the old tabs (also written by the agents). */

afterEach(() => vi.unstubAllGlobals());

const task = (name: string, title: string) => ({
  name, title, status: "todo", type: "development", objective: "", context: "", criteria: [], constraints: "", references: [], tests: null,
});
const BORN = task("agent-task-note.md", "Note");
const ORPHAN = task("agent-task-orfano.md", "Orfano");
const ACTIVITY = {
  name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", description: "La 2.0", learned: "", references: [],
  items: [{ text: "Note", done: false, priority: null, due: null, agent_task: BORN.name }], agent_tasks: [BORN.name],
};

/** Where the router is (path and query), to check the redirects. */
function Where() {
  const location = useLocation();
  return <div data-testid="where">{location.pathname + location.search}</div>;
}

function api(extra: Record<string, unknown> = {}) {
  mockApi({
    "GET /projects/acme/today": { date: "2026-11-12", due_soon_days: 3, waiting: [], overdue: [], due_soon: [], to_close: [] },
    "GET /projects/acme/activities": [ACTIVITY],
    "GET /projects/acme/agent-tasks": [BORN, ORPHAN],
    "GET /projects/acme/notes": [{ name: "decisioni.md", kind: "note", size: 1, modified_at: "2026-11-12T10:00:00Z", note_type: "generic" }],
    "GET /projects/acme/notes/decisioni.md": { name: "decisioni.md", content: "# Decisioni" },
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/chatbots": [],
    "GET /projects/acme/wip": { content: "", pending_words: 0 },
    "GET /projects/acme/data-settings": { visible_note_types: ["generic", "agent_task", "activity"], files_visible: true, due_soon_days: 3 },
    "GET /projects/acme/files": [],
    "GET /projects/acme/atlassian": { base_url: "", email: "", has_token: false, jira_project_key: "", confluence_space_key: "" },
    "GET /projects/acme/git/repositories": [],
    ...extra,
  });
}

const renderAt = (route: string) =>
  renderPage(<><Routes>{zoneRoutes()}</Routes><Routes><Route path="*" element={<Where />} /></Routes></>, { route });

describe("«Lavoro»", () => {
  it("opens on the activities with «Oggi» on top, and has «Tutti i task» and the WIP", async () => {
    api();
    renderAt("/projects/acme/work");

    expect(await screen.findByRole("tab", { name: /Attività/, selected: true })).toBeInTheDocument();
    expect(screen.getByText("📌 Oggi")).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "🤖 Tutti i task (2)" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /WIP/ }));
    expect(await screen.findByPlaceholderText(/Scrivi di getto/)).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/acme/work?note=wip.md");
  });

  it("a task born from an activity opens inside it; one born from nothing in «Tutti i task»", async () => {
    api();
    renderAt(`/projects/acme/work?note=${BORN.name}`);

    expect(await screen.findByRole("button", { name: "← Rilascio" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Attività/, selected: true })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "← Rilascio" }));
    expect(await screen.findByDisplayValue("La 2.0")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Tutti i task/ }));
    fireEvent.click(await screen.findByText("Orfano"));
    expect(await screen.findByDisplayValue("Orfano")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Tutti i task/, selected: true })).toBeInTheDocument();
  });

  it("a note opened from «Lavoro» goes to «Progetto»", async () => {
    api();
    renderAt("/projects/acme/work?note=decisioni.md");

    expect(await screen.findByDisplayValue("# Decisioni")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/projects/acme/project?note=decisioni.md");
    expect(screen.getByRole("tab", { name: /Note/, selected: true })).toBeInTheDocument();
  });
});

describe("the links of the old tabs", () => {
  it.each([
    ["/projects/acme/data", "/projects/acme/work"],
    [`/projects/acme/data?note=${BORN.name}`, `/projects/acme/work?note=${BORN.name}`],
    ["/projects/acme/data?note=decisioni.md", "/projects/acme/project?note=decisioni.md"],
    ["/projects/acme/git", "/projects/acme/project?tab=git"],
    ["/projects/acme/settings", "/projects/acme/project?tab=settings"],
  ])("%s → %s", async (from, to) => {
    api();
    renderAt(from);
    expect(await screen.findByTestId("where")).toHaveTextContent(to);
  });

  it("an activity linked from «Progetto» goes back to «Lavoro»", async () => {
    api();
    renderAt(`/projects/acme/project?note=${ACTIVITY.name}`);

    expect(await screen.findByDisplayValue("La 2.0")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`/projects/acme/work?note=${ACTIVITY.name}`);
  });
});
