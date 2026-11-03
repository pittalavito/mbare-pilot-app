import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Chatbot, Message } from "../../api/chat";
import { mockApi, renderPage } from "../../test/render";
import { ChatTab } from "../chat/ChatTab";
import { DataTab } from "./DataTab";
import { noteOfLink } from "./RefinerPanel";

afterEach(() => vi.unstubAllGlobals());

const bot = (id: number, name: string, kind: Chatbot["kind"]): Chatbot => ({
  id, project_name: "acme", name, kind, description: kind === "refiner" ? "Ti aiuta a rifinire gli agent task" : "", system_prompt: "x",
  prompt_version: 1, model: "mock/echo", max_steps: 4, tool_names: kind === "refiner" ? ["create_code_reference"] : [],
});
const REFINER = bot(7, "Refiner", "refiner");
const SECRETARY = bot(8, "Segretario", "secretary");
const NOTE = "code-reference-todo-mbare-pilot.md";
const message = (id: number, role: string, content: string): Message => ({
  id, conversation_id: 3, role, content, run_id: null, created_at: "2026-11-02T10:00:00Z",
});
const REFERENCE = {
  name: NOTE, title: "TODO Mbare Pilot", kind: "code_reference", source: "todoMbarePilot", source_url: "", repository: "", path: "", lines: "",
  content: "### api/login.py\n- riga 2: Rifattorizza", linked_from: [],
};

function renderData(extra: Record<string, unknown> = {}) {
  const sent = vi.fn(() => ({}));
  let replied = false;
  mockApi({
    "GET /projects/acme/notes": [],
    "GET /projects/acme/agent-tasks": [],
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/chatbots": [SECRETARY, REFINER],
    "GET /chatbots/7/conversations": () => (replied ? [{ id: 3, chatbot_id: 7, title: "Todo del codice", created_at: "", updated_at: "" }] : []),
    "POST /chatbots/7/conversations": { id: 3, chatbot_id: 7, title: "", created_at: "", updated_at: "" },
    "POST /conversations/3/messages": () => { replied = true; return sent(); },
    "GET /conversations/3/messages": () => [
      message(1, "user", "raccogli i todo del codice"),
      message(2, "assistant", `Fatto: 1 commento in 1 file, nota nuova: [TODO Mbare Pilot](/projects/acme/data?note=${NOTE}). Vedi anche [Copilot](/projects/acme/copilot).`),
    ],
    "GET /projects/acme/references": [REFERENCE],
    ...extra,
  });
  renderPage(<Routes><Route path="/projects/:project/data" element={<DataTab />} /></Routes>, { route: "/projects/acme/data" });
  return sent;
}

describe("RefinerPanel", () => {
  it("chats with the refiner next to the agent tasks and opens the note it wrote in place", async () => {
    const sent = renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));

    expect(await screen.findByText("Ti aiuta a rifinire gli agent task")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Scrivi a Refiner/), { target: { value: "raccogli i todo del codice" } });
    fireEvent.click(screen.getByRole("button", { name: "Invia" }));
    await waitFor(() => expect(sent).toHaveBeenCalled());

    fireEvent.click(await screen.findByRole("link", { name: "TODO Mbare Pilot" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(NOTE)).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue(/riga 2: Rifattorizza/)).toBeInTheDocument(); // editable
    expect(await screen.findByRole("textbox", { name: "Conversazione" })).toHaveValue("Todo del codice"); // the new one, now listed
  });

  it("a link to a reference that is gone says so; it can be hidden", async () => {
    renderData({ "GET /projects/acme/references": [] });
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    fireEvent.change(await screen.findByPlaceholderText(/Scrivi a Refiner/), { target: { value: "vai" } });
    fireEvent.click(screen.getByRole("button", { name: "Invia" }));

    fireEvent.click(await screen.findByRole("link", { name: "TODO Mbare Pilot" }));
    expect(await screen.findByText(`Il riferimento ${NOTE} non c'è più.`)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Nascondi il Refiner" }));
    expect(screen.queryByPlaceholderText(/Scrivi a Refiner/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Mostra il Refiner/ }));
    expect(await screen.findByPlaceholderText(/Scrivi a Refiner/)).toBeInTheDocument();
  });

  it("without a refiner says where it comes from", async () => {
    renderData({ "GET /projects/acme/chatbots": [SECRETARY] });
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));

    expect(await screen.findByText(/Nessun Refiner nel progetto/)).toBeInTheDocument();
  });

  it("is not in the Chat tab", async () => {
    mockApi({
      "GET /projects/acme/chatbots": [REFINER, SECRETARY],
      "GET /chatbots/8/conversations": [],
      "GET /chatbots/8/automation-cache": [],
    });
    renderPage(<Routes><Route path="/projects/:project/chat" element={<ChatTab />} /></Routes>, { route: "/projects/acme/chat?bot=7" });

    expect(await screen.findByPlaceholderText(/Scrivi a Segretario/)).toBeInTheDocument(); // ?bot=7 is the refiner: not here
    expect(screen.queryByText("Refiner")).not.toBeInTheDocument();
  });

  it("reads the note of an app link only", () => {
    expect(noteOfLink(`/projects/acme/data?note=${NOTE}`)).toBe(NOTE);
    expect(noteOfLink("/projects/acme/copilot?session=1")).toBeNull();
    expect(noteOfLink(`https://altro.it/projects/acme/data?note=${NOTE}`)).toBeNull();
  });
});
