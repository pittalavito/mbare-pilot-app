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
        <Route path="work" element={<div>contenuto lavoro</div>} />
        <Route path="project" element={<div>contenuto progetto</div>} />
      </Route>
    </Routes>,
    { route },
  );
}

describe("ProjectPage", () => {
  it("opens on «Lavoro» and shows the three zones", async () => {
    mockApi({ "GET /projects/Gestionali Navi": PROJECT });
    renderProject("/projects/Gestionali%20Navi");

    expect(await screen.findByText("contenuto lavoro")).toBeInTheDocument();
    expect(screen.getByText("✨ Creato da zero", { exact: false })).toBeInTheDocument();
    for (const tab of ["📋 Lavoro", "⚙️ Automation", "🗂️ Progetto"]) {
      expect(screen.getByRole("tab", { name: tab })).toBeInTheDocument();
    }
    expect(screen.getByRole("tab", { name: "📋 Lavoro" })).toHaveAttribute("aria-selected", "true");
  });

  it("selects the zone of the URL", async () => {
    mockApi({ "GET /projects/Gestionali Navi": PROJECT });
    renderProject("/projects/Gestionali%20Navi/project");

    expect(await screen.findByText("contenuto progetto")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "🗂️ Progetto" })).toHaveAttribute("aria-selected", "true");
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
