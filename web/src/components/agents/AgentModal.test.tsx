import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { AgentModal } from "./AgentModal";

afterEach(() => vi.unstubAllGlobals());

const AGENT = {
  name: "pianificatore", project_name: null, description: "", role_name: "pianificatore", prompt_id: 1, prompt_version: 1,
  model: "openai/gpt-4o-mini", max_steps: 1, tool_names: [], output: "plan", blocked_reason: null,
};

describe("the agent window", () => {
  it("shows and saves the structured answer", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...AGENT, ...(await request.json()) }));
    mockApi({
      "GET /roles": [{ name: "pianificatore", project_name: null, description: "", active: true }],
      "GET /roles/pianificatore/prompts": [{ id: 1, role_name: "pianificatore", version: 1, text: "Sei il Pianificatore.", active: true }],
      "GET /tools": [],
      "GET /models/choices": [{ key: "openai/gpt-4o-mini", label: "gpt-4o-mini" }],
      "GET /agents/outputs": [{ name: "plan", description: "Pianificatore" }, { name: "draft", description: "Da riferimenti" }],
      "PUT /agents/pianificatore": saved,
    });
    renderPage(<AgentModal scope={null} agent={AGENT} opened onClose={() => {}} />);

    const [select] = await screen.findAllByRole("textbox", { name: /Risposta strutturata/ });
    await waitFor(() => expect(select).toHaveValue("plan — Pianificatore"));
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ output: "plan", max_steps: 1 });
  });
});
