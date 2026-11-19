import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { RoadmapPage } from "./RoadmapPage";

afterEach(() => vi.unstubAllGlobals());

describe("«🚀 Mbare Pilot» (plan 30)", () => {
  it("shows the goal, the vision and the board by status", async () => {
    mockApi({
      "GET /roadmap": {
        goal: "Demo datapizza", vision: "Qui si apriranno bug e attività sull'app.",
        items: [
          { title: "Uso quotidiano", description: "Ogni giorno", kind: "uso", owner: "tu", status: "in_progress", feasibility: "" },
          { title: "Integrazione Bitbucket", description: "", kind: "integrazione", owner: "agente remoto", status: "todo", feasibility: "Fattibilità già verificata." },
          { title: "Piano 29", description: "", kind: "rag", owner: "claude", status: "done", feasibility: "" },
        ],
      },
    });
    renderPage(<RoadmapPage />);

    expect(await screen.findByText("🎯 Demo datapizza")).toBeInTheDocument();
    expect(screen.getByText("2 attività alla demo")).toBeInTheDocument();
    expect(screen.getByText(/Qui si apriranno bug/)).toBeInTheDocument();
    expect(within(screen.getByTestId("column-in_progress")).getByText("Uso quotidiano")).toBeInTheDocument();
    const todo = within(screen.getByTestId("column-todo"));
    expect(todo.getByText("Integrazione Bitbucket")).toBeInTheDocument();
    expect(todo.getByText("✓ Fattibilità già verificata.")).toBeInTheDocument();
    expect(todo.getByText("🛰 agente remoto")).toBeInTheDocument();
    expect(within(screen.getByTestId("column-done")).getByText("RAG")).toBeInTheDocument();
  });

  it("without activities says where to write them", async () => {
    mockApi({ "GET /roadmap": { goal: "", vision: "", items: [] } });
    renderPage(<RoadmapPage />);
    expect(await screen.findByText(/scrivile in roadmap.yml/)).toBeInTheDocument();
  });
});
