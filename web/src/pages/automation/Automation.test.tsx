import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Pipeline, Run } from "../../api/automation";
import { mockApi, renderPage } from "../../test/render";
import { AutomationEditor } from "./AutomationEditor";
import { AutomationTab } from "./AutomationTab";

afterEach(() => vi.unstubAllGlobals());

const step = (name: string, x: number) => ({
  name, kind: "function", input_template: "{input}", agent: null, agent_config_name: null,
  function_name: "git_status", params: {}, position_x: x, position_y: 0,
});

const PIPELINE: Pipeline = {
  id: 7, project_name: "acme", name: "Controllo", description: "Verifica il repo", active: true,
  steps: [step("Stato", 240), step("Pull", 480)],
  edges: [
    { source: "input", target: "Stato", condition: "always", value: "" },
    { source: "Stato", target: "Pull", condition: "contains", value: "OK" },
  ],
};

const RUN: Run = {
  id: 3, pipeline_id: 7, status: "done", input: "vai", output: "fatto", error: null,
  created_at: "2026-10-25T10:00:00Z", started_at: "2026-10-25T10:00:00Z", finished_at: "2026-10-25T10:00:02Z",
  steps: [{ position: 0, name: "Stato", kind: "function", status: "done", input: "vai", output: "tutto OK", error: null,
    agent_run_id: null, started_at: "2026-10-25T10:00:00Z", finished_at: "2026-10-25T10:00:01Z" }],
};

const CATALOGS = {
  "GET /functions": [{ name: "git_status", description: "Lo stato del repo", params: [] }],
  "GET /models/choices": { choices: ["mock/echo"], usable: ["mock/echo"] },
  "GET /tools": [],
  "GET /agents": [],
};

function renderTab(route = "/projects/acme/automation") {
  return renderPage(
    <Routes>
      <Route path="/projects/:project/automation" element={<AutomationTab />} />
      <Route path="/projects/:project/automation/new" element={<div>editor nuova</div>} />
    </Routes>,
    { route },
  );
}

function renderEditor(route: string) {
  return renderPage(
    <Routes>
      <Route path="/projects/:project/automation" element={<div>tab automation</div>} />
      <Route path="/projects/:project/automation/new" element={<AutomationEditor />} />
      <Route path="/projects/:project/automation/:pipelineId/edit" element={<AutomationEditor />} />
    </Routes>,
    { route },
  );
}

describe("AutomationTab", () => {
  it("invites to create the first automation", async () => {
    mockApi({ "GET /projects/acme/pipelines": [] });
    renderTab();

    fireEvent.click(await screen.findByRole("link", { name: /Nuova automation/ }));

    expect(await screen.findByText("editor nuova")).toBeInTheDocument();
  });

  it("shows the automation, its history and queues a run with the input", async () => {
    const enqueued = vi.fn(async (request: Request) => ({ ...RUN, id: 4, status: "queued", steps: [], input: (await request.json()).input }));
    mockApi({
      "GET /projects/acme/pipelines": [PIPELINE],
      "GET /pipelines/7/runs": [RUN],
      "POST /pipelines/7/runs": enqueued,
      "GET /admin/worker": { status: "stopped", pid: null, workers: [] },
    });
    renderTab();

    expect(await screen.findByText(/2 step, 2 collegamenti · 1 con condizione/)).toBeInTheDocument();
    expect(await screen.findByText(/Controllo · .* · 2\.0 s/)).toBeInTheDocument();
    expect(await screen.findByText(/Nessun worker attivo/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Input"), { target: { value: "controlla main" } });
    fireEvent.click(screen.getByRole("button", { name: /Esegui/ }));

    await waitFor(() => expect(enqueued).toHaveBeenCalled());
    expect(await enqueued.mock.results[0].value).toMatchObject({ input: "controlla main" });
  });
});

describe("AutomationEditor", () => {
  it("saves the edited automation with its edges by name", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...PIPELINE, ...(await request.json()) }));
    mockApi({ ...CATALOGS, "GET /projects/acme/pipelines": [PIPELINE], "PUT /pipelines/7": saved });
    renderEditor("/projects/acme/automation/7/edit");

    const name = await screen.findByLabelText(/Nome/);
    fireEvent.change(name, { target: { value: "Controllo serale" } });
    fireEvent.click(screen.getByRole("button", { name: /Salva/ }));

    expect(await screen.findByText("tab automation")).toBeInTheDocument();
    const body = await saved.mock.results[0].value;
    expect(body).toMatchObject({ name: "Controllo serale", active: true });
    expect(body.edges).toEqual(PIPELINE.edges);
    expect(body.steps.map((s: { name: string }) => s.name)).toEqual(["Stato", "Pull"]);
  });

  it("refuses to save steps that are not connected", async () => {
    const created = vi.fn();
    mockApi({ ...CATALOGS, "POST /projects/acme/pipelines": created });
    renderEditor("/projects/acme/automation/new");

    fireEvent.change(await screen.findByLabelText(/Nome/), { target: { value: "Nuova" } });
    fireEvent.click(screen.getByRole("button", { name: /Funzione \(codice\)/ }));
    expect(await screen.findByDisplayValue("Step 1")).toBeInTheDocument(); // its panel is open
    fireEvent.click(screen.getByRole("button", { name: /Salva/ }));

    expect(await screen.findByText(/parti da «input» e trascina fino al primo step/)).toBeInTheDocument();
    expect(created).not.toHaveBeenCalled();
  });
});
