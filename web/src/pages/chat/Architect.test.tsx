import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { AutomationEditor } from "../automation/AutomationEditor";
import { PROJECT_API, projectRoutes } from "../../test/zones";

/** Blocco 05: the Architect's proposal in the chat (graph, «Salva») and «Esporta YAML» in the editor. */

afterEach(() => vi.unstubAllGlobals());

const YAML = "name: Stato\nsteps:\n  - {name: Stato, function: git_status}\n";
const step = (name: string) => ({
  name, kind: "function", input_template: "{input}", agent: null, agent_config_name: null, function_name: "git_status", params: {},
  position_x: 0, position_y: 0,
});
const CHECK = {
  name: "Stato", description: "Lo stato dei repository", active: true, steps: [step("Stato")],
  edges: [{ source: "input", target: "Stato", condition: "always", value: "" }], replaces: null, system: false,
};
const ARCHITECT = {
  id: 5, project_name: "acme", name: "Architetto", kind: "automation", description: "", system_prompt: "x", prompt_version: 1,
  model: "mock/echo", max_steps: 10, tool_names: [], automation_cache: false,
};
const ANSWER = `Ecco l'automation: legge lo stato.\n\n\`\`\`automation\n${YAML}\`\`\`\n\nVa bene?`;

function api(check: unknown = CHECK) {
  const saved = vi.fn(async (request: Request) => ({ ...CHECK, id: 11, project_name: "acme", ...(await request.json()) }));
  mockApi({
    ...PROJECT_API,
    "GET /projects/acme/chatbots": [ARCHITECT],
    "GET /chatbots/5/conversations": [{ id: 9, chatbot_id: 5, title: "Nuova", created_at: "2026-11-11T10:00:00Z" }],
    "GET /chatbots/5/automation-cache": [],
    "GET /projects/acme/pipelines": [],
    "GET /conversations/9/messages": [
      { id: 1, conversation_id: 9, role: "user", content: "fammi un'automation dello stato", created_at: "2026-11-11T10:00:00Z", agent_run_id: null },
      { id: 2, conversation_id: 9, role: "assistant", content: ANSWER, created_at: "2026-11-11T10:00:01Z", agent_run_id: null },
    ],
    "POST /projects/acme/pipelines/yaml/check": check instanceof Response ? () => check : check,
    "POST /projects/acme/pipelines/yaml": saved,
  });
  return { saved };
}

/** The zone Automation: the Architect is in the agent panel, with its latest conversation. */
const renderChat = () => renderPage(<Routes>{projectRoutes()}</Routes>, { route: "/projects/acme/automation" });

describe("the Architect's proposal", () => {
  it("shows the graph and saves only on «Salva»", async () => {
    const { saved } = api();
    renderChat();

    const card = await screen.findByTestId("automation-proposal");
    expect(await within(card).findByText("⚙️ Stato")).toBeInTheDocument();
    expect(within(card).getByText("nuova")).toBeInTheDocument();
    expect(within(card).getByText(/input → Stato/)).toBeInTheDocument();
    expect(saved).not.toHaveBeenCalled();
    expect(screen.getByText(/Va bene\?/)).toBeInTheDocument(); // the rest of the message stays

    fireEvent.click(within(card).getByRole("button", { name: /Salva/ }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ yaml: YAML.trimEnd() });
    expect(await within(card).findByRole("link", { name: /Salvata: aprila/ })).toHaveAttribute("href", "/projects/acme/automation?id=11");
  });

  it("warns on a system automation and on one that replaces another", async () => {
    api({ ...CHECK, name: "Verifica sviluppo", replaces: 3, system: true });
    renderChat();
    const card = await screen.findByTestId("automation-proposal");
    expect(await within(card).findByText("modifica quella che c'è")).toBeInTheDocument();
    expect(within(card).getByText(/la lancia l'app da sola/)).toBeInTheDocument();
  });

  it("an invalid proposal shows the reason and its YAML, without «Salva»", async () => {
    api(new Response(JSON.stringify({ detail: "Step 1 (Stato): la funzione non_esiste non esiste (più) nel codice." }), { status: 400 }));
    renderChat();
    const card = await screen.findByTestId("automation-proposal");
    expect(await within(card).findByText(/non_esiste non esiste/)).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /Salva/ })).not.toBeInTheDocument();
  });
});

describe("«Esporta YAML»", () => {
  it("shows the saved automation in the definitions' format", async () => {
    const PIPELINE = { ...CHECK, id: 7, project_name: "acme" };
    mockApi({
      "GET /functions": [{ name: "git_status", description: "Lo stato", params: [] }],
      "GET /models/choices": { choices: ["mock/echo"], usable: ["mock/echo"] },
      "GET /tools": [],
      "GET /agents": [],
      "GET /projects/acme/pipelines": [PIPELINE],
      "GET /pipelines/7/yaml": { yaml: "automations:\n- name: Stato\n" },
    });
    renderPage(
      <Routes><Route path="/projects/:project/automation/:pipelineId/edit" element={<AutomationEditor />} /></Routes>,
      { route: "/projects/acme/automation/7/edit" },
    );

    fireEvent.click(await screen.findByRole("button", { name: /Esporta YAML/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/automations:/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Copia" })).toBeInTheDocument();
  });
});
