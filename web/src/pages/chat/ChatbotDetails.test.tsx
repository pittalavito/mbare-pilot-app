import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Chatbot } from "../../api/chat";
import { mockApi, renderPage } from "../../test/render";
import { ChatbotDetails } from "./ChatbotDetails";

afterEach(() => vi.unstubAllGlobals());

const BOT = {
  id: 7, project_name: "acme", name: "Dev", kind: "operator", description: "", system_prompt: "Dev dell'app.", prompt_version: 1,
  model: "openai/gpt-4o", max_steps: 12, tool_names: ["git_status"], automation_cache: false, origin: "tuo",
} as Chatbot;

describe("ChatbotDetails (plan 28)", () => {
  it("saves the prompt and goes back to the app's default", async () => {
    const saved = vi.fn(async (request: Request) => ({ ...BOT, ...(await request.json()) }));
    const reverted = vi.fn(() => ({ ...BOT, origin: "app" }));
    mockApi({ "PUT /chatbots/7": saved, "POST /chatbots/7/revert": reverted, "GET /models": [], "GET /catalog/models": [] });
    renderPage(<ChatbotDetails chatbot={BOT} opened onClose={() => undefined} />);

    expect(await screen.findByText("tuo")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("System prompt"), { target: { value: "Dev mio." } });
    fireEvent.click(screen.getByRole("button", { name: "Salva prompt" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ system_prompt: "Dev mio.", name: "Dev", tool_names: ["git_status"] });

    fireEvent.click(screen.getByRole("button", { name: /Torna al default/ }));
    await waitFor(() => expect(reverted).toHaveBeenCalled());
  });
});
