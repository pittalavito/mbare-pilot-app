import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { ProjectPage } from "./ProjectPage";

afterEach(() => vi.unstubAllGlobals());

const PROJECT = {
  name: "Gestionali Navi",
  description: "",
  source: "scratch",
  root_path: "/code/navi",
  embedding_model: "openai/text-embedding-3-small",
  created_at: "2026-10-25T10:00:00Z",
  folder_exists: true,
};

function renderProject(route: string) {
  return renderPage(
    <Routes>
      <Route path="/projects/:project" element={<ProjectPage />}>
        <Route path="chat" element={<div>contenuto chat</div>} />
        <Route path="git" element={<div>contenuto git</div>} />
      </Route>
    </Routes>,
    { route },
  );
}

describe("ProjectPage", () => {
  it("opens on the chat tab and shows only the tabs that apply", async () => {
    mockApi({
      "GET /projects/Gestionali Navi": PROJECT,
      "GET /projects/Gestionali Navi/atlassian": { base_url: "", email: "", has_token: false, jira_project_key: "", confluence_space_key: "" },
    });
    renderProject("/projects/Gestionali%20Navi");

    expect(await screen.findByText("contenuto chat")).toBeInTheDocument();
    expect(screen.getByText("✨ Creato da zero", { exact: false })).toBeInTheDocument();
    for (const tab of ["💬 Chat", "⚙️ Automation", "🗂️ Dati", "🌿 Git", "🔧 Impostazioni"]) {
      expect(screen.getByRole("tab", { name: tab })).toBeInTheDocument();
    }
    expect(screen.queryByRole("tab", { name: "🔷 Atlassian" })).not.toBeInTheDocument();
  });

  it("shows the Atlassian tab when the site is configured, and the tab of the URL", async () => {
    mockApi({
      "GET /projects/Gestionali Navi": PROJECT,
      "GET /projects/Gestionali Navi/atlassian": {
        base_url: "https://x.atlassian.net", email: "me@x.it", has_token: true, jira_project_key: "", confluence_space_key: "",
      },
    });
    renderProject("/projects/Gestionali%20Navi/git");

    expect(await screen.findByText("contenuto git")).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "🔷 Atlassian" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "🌿 Git" })).toHaveAttribute("aria-selected", "true");
  });

  it("explains an unknown project", async () => {
    mockApi({
      "GET /projects/Nessuno": () => new Response(JSON.stringify({ detail: "Progetto non trovato: Nessuno" }), { status: 404 }),
      "GET /projects/Nessuno/atlassian": () => new Response("{}", { status: 404 }),
    });
    renderProject("/projects/Nessuno");

    expect(await screen.findByText("Progetto non trovato: Nessuno")).toBeInTheDocument();
  });
});
