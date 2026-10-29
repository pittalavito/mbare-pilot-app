import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Chatbot, AutomationCacheEntry, Message } from "../../api/chat";
import { mockApi, renderPage } from "../../test/render";
import { ChatTab } from "./ChatTab";

afterEach(() => vi.unstubAllGlobals());

const CHATBOT: Chatbot = {
  id: 5, project_name: "acme", name: "Navi bot", kind: "automation", description: "", system_prompt: "Rispondi breve.",
  prompt_version: 2, model: "mock/echo", max_steps: 4, tool_names: ["run_automation"],
};
const CONVERSATION = { id: 9, chatbot_id: 5, title: "Stato del repo", created_at: "2026-10-25T10:00:00Z", updated_at: "2026-10-25T10:00:00Z" };
const message = (id: number, role: string, content: string): Message => ({
  id, conversation_id: 9, role, content, run_id: null, created_at: "2026-10-25T10:00:00Z",
});
const PIPELINE = { id: 7, project_name: "acme", name: "Git status", description: "", active: true, steps: [{ name: "S", kind: "function", params: {} }], edges: [] };
const CACHE_ENTRY: AutomationCacheEntry = {
  id: 1, chatbot_id: 5, message_id: 11, text: "com'è il repo?", pipeline_id: 7, pipeline_input: "main", hits: 3, created_at: "2026-10-25T10:00:00Z",
};

const BASE = {
  "GET /projects/acme/chatbots": [CHATBOT],
  "GET /chatbots/5/conversations": [CONVERSATION],
  "GET /chatbots/5/automation-cache": [],
  "GET /projects/acme/pipelines": [PIPELINE],
};

const renderChat = (route = "/projects/acme/chat") =>
  renderPage(<Routes><Route path="/projects/:project/chat" element={<ChatTab />} /></Routes>, { route });

describe("ChatTab", () => {
  it("lists the project's chatbots and opens the chosen one with its conversations", async () => {
    const OTHER: Chatbot = { ...CHATBOT, id: 6, name: "Automazioni", description: "Lancia le automation" };
    mockApi({
      ...BASE,
      "GET /projects/acme/chatbots": [OTHER, CHATBOT],
      "GET /chatbots/6/conversations": [],
      "GET /chatbots/6/automation-cache": [],
    });
    renderChat("/projects/acme/chat?bot=5");

    expect(await screen.findByText("Stato del repo")).toBeInTheDocument(); // ?bot=5 is open, not the first
    expect(screen.getByText("Lancia le automation")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Automazioni"));

    expect(await screen.findByText("Nessuna conversazione.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Scrivi a Automazioni/)).toBeInTheDocument();
  });

  it("without chatbots says where they come from: they are not created here", async () => {
    mockApi({ "GET /projects/acme/chatbots": [] });
    renderChat();

    expect(await screen.findByText(/i chatbot di default si creano all'avvio/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Crea|Nuovo chatbot/ })).not.toBeInTheDocument();
  });

  it("shows the open conversation with the replies and the cache of a message", async () => {
    mockApi({
      ...BASE,
      "GET /chatbots/5/automation-cache": [CACHE_ENTRY],
      "GET /conversations/9/messages": [
        message(10, "user", "ciao"), message(12, "assistant", "**Ciao!**"),
        message(11, "user", "com'è il repo?"), message(13, "assistant", "⚡ Git status avviata"),
      ],
    });
    renderChat("/projects/acme/chat?c=9");

    expect(await screen.findByText("Ciao!")).toHaveProperty("tagName", "STRONG"); // markdown
    expect(screen.getByText(/In cache →/)).toHaveTextContent("In cache → Git status · input «main» · usata 3 volte");
    expect(screen.getAllByRole("button", { name: /Metti in cache/ })).toHaveLength(1); // only the message not in cache
  });

  it("a custom chatbot has no automation cache; its details are read-only", async () => {
    mockApi({
      ...BASE,
      "GET /projects/acme/chatbots": [{ ...CHATBOT, kind: "custom", tool_names: ["git_status"] }],
      "GET /conversations/9/messages": [message(10, "user", "ciao"), message(12, "assistant", "Ciao!")],
    });
    renderChat("/projects/acme/chat?c=9");

    expect(await screen.findByText("Ciao!")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Metti in cache/ })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Scrivi a Navi bot/)).not.toHaveAttribute("placeholder", expect.stringContaining("cache"));

    fireEvent.click(screen.getByRole("button", { name: /Dettagli/ }));
    expect(await screen.findByText("Rispondi breve.")).toBeInTheDocument();
    expect(screen.getByText(/Sola lettura/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Salva|Elimina chatbot/ })).not.toBeInTheDocument();
  });

  it("creates the conversation on the first message and opens it", async () => {
    let sent: unknown;
    let messages: Message[] = [];
    mockApi({
      ...BASE,
      "GET /chatbots/5/conversations": () => (messages.length ? [CONVERSATION] : []),
      "POST /chatbots/5/conversations": CONVERSATION,
      "POST /conversations/9/messages": async (request: Request) => {
        sent = await request.json();
        messages = [message(10, "user", "ciao"), message(11, "assistant", "eco: ciao")];
        return messages[1];
      },
      "GET /conversations/9/messages": () => messages,
    });
    renderChat();

    const input = await screen.findByPlaceholderText(/Scrivi a Navi bot/);
    fireEvent.change(input, { target: { value: "ciao" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(await screen.findByText("eco: ciao")).toBeInTheDocument();
    expect(sent).toEqual({ text: "ciao" });
    await waitFor(() => expect(screen.getByRole("button", { name: /Elimina conversazione/ })).toBeInTheDocument());
  });

  it("puts a message in the cache with the automation and the fixed input", async () => {
    const added = vi.fn(async (request: Request) => ({ ...CACHE_ENTRY, ...(await request.json()) }));
    mockApi({
      ...BASE,
      "GET /conversations/9/messages": [message(11, "user", "com'è il repo?"), message(12, "assistant", "Ho lanciato Git status")],
      "POST /messages/11/automation-cache": added,
    });
    renderChat("/projects/acme/chat?c=9");

    fireEvent.click(await screen.findByRole("button", { name: /Metti in cache/ }));
    fireEvent.change(await screen.findByLabelText(/Input fisso/), { target: { value: "main" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(added).toHaveBeenCalled());
    expect(await added.mock.results[0].value).toMatchObject({ pipeline_id: 7, input: "main" });
  });
});
