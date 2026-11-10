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

const CREATED = { name: "agent-task-login.md", title: "Login", status: "created", type: "development", objective: "", context: "",
  criteria: [], constraints: "", references: [] };

function renderData(extra: Record<string, unknown> = {}) {
  const sent = vi.fn(() => ({}));
  let replied = false;
  mockApi({
    "GET /projects/acme/notes": [],
    "GET /projects/acme/agent-tasks": [CREATED],
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

  it("changes the refiner's model from its details", async () => {
    let refiner = REFINER;
    const patched = vi.fn(async (request: Request) => {
      refiner = { ...refiner, model: (await request.json()).model };
      return refiner;
    });
    renderData({
      "GET /projects/acme/chatbots": () => [SECRETARY, refiner],
      "GET /models/choices": { choices: ["mock/echo", "openai/gpt-4o"], usable: ["mock/echo", "openai/gpt-4o"] },
      "PATCH /chatbots/7/model": patched,
    });
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    expect(await screen.findByText("mock/echo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Dettagli/ }));
    const dialog = await screen.findByRole("dialog", { name: /Chatbot «Refiner»/ });
    fireEvent.click(within(dialog).getByRole("textbox", { name: "Modello" }));
    fireEvent.click(await screen.findByRole("option", { name: "openai/gpt-4o" }));
    const save = within(dialog).getByRole("button", { name: "Salva" });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);

    expect(await within(dialog).findByText(/Modello salvato/)).toBeInTheDocument();
    expect(patched).toHaveBeenCalledTimes(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "" })); // close
    expect(await screen.findByText("openai/gpt-4o")).toBeInTheDocument(); // the panel shows the new model
  });

  it("sends the open task with every message and the editor follows what the refiner writes", async () => {
    const task = { name: "agent-task-login.md", title: "Login", status: "created", type: "development", objective: "", context: "",
      criteria: [], constraints: "", references: [] };
    let current = task;
    const bodies: unknown[] = [];
    renderData({
      "GET /projects/acme/agent-tasks": () => [current],
      "POST /conversations/3/messages": async (request: Request) => {
        bodies.push(await request.json());
        current = { ...current, status: "refinement", objective: "Login sotto il secondo" }; // what the button and update_agent_task do
        return {};
      },
    });
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));

    expect(await screen.findByText(/Task aperto:/)).toHaveTextContent("Task aperto: Login");
    fireEvent.change(screen.getByPlaceholderText(/Scrivi a Refiner/), { target: { value: "rifinisci questo task" } });
    fireEvent.click(screen.getByRole("button", { name: "Invia" }));

    await waitFor(() => expect(bodies).toEqual([{ text: "rifinisci questo task", open_note: "agent-task-login.md" }]));
    expect(await screen.findByDisplayValue("Login sotto il secondo")).toBeInTheDocument(); // reloaded: nothing unsaved
    expect(screen.queryByText(/è cambiato mentre lo modificavi/)).not.toBeInTheDocument();
  });

  it("warns instead of reloading when the open task has unsaved changes", async () => {
    const task = { name: "agent-task-login.md", title: "Login", status: "refinement", type: "development", objective: "", context: "",
      criteria: [], constraints: "", references: [] };
    let current = task;
    renderData({
      "GET /projects/acme/agent-tasks": () => [current],
      "POST /conversations/3/messages": () => { current = { ...current, objective: "Scritto dal Refiner" }; return {}; },
    });
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    fireEvent.change(await screen.findByLabelText("Vincoli", { exact: false }), { target: { value: "mio vincolo" } });

    fireEvent.change(await screen.findByPlaceholderText(/Scrivi a Refiner/), { target: { value: "scrivi l'obiettivo" } });
    fireEvent.click(screen.getByRole("button", { name: "Invia" }));

    expect(await screen.findByText(/è cambiato mentre lo modificavi/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("mio vincolo")).toBeInTheDocument(); // my change is kept
    fireEvent.click(screen.getByRole("button", { name: /Ricarica/ }));
    expect(await screen.findByDisplayValue("Scritto dal Refiner")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("mio vincolo")).not.toBeInTheDocument();
  });

  it("is there only for a created or in refinement task", async () => {
    const todo = { ...CREATED, name: "agent-task-pronto.md", title: "Pronto", status: "todo" };
    renderData({ "GET /projects/acme/agent-tasks": [CREATED, todo] });
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    expect(await screen.findByPlaceholderText(/Scrivi a Refiner/)).toBeInTheDocument(); // Login, created, is open

    fireEvent.click(screen.getByText("Pronto", { selector: ".mantine-NavLink-label" }));

    await waitFor(() => expect(screen.queryByPlaceholderText(/Scrivi a Refiner/)).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Refiner/ })).not.toBeInTheDocument(); // nor its show/hide
  });

  it("«Rifinisci con il Refiner» puts the request in its box, not sent", async () => {
    const sent = renderData();
    fireEvent.click(await screen.findByRole("tab", { name: /Agent task/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Nascondi il Refiner" }));

    fireEvent.click(screen.getByRole("button", { name: /Rifinisci con il Refiner/ }));

    expect(await screen.findByPlaceholderText(/Scrivi a Refiner/)).toHaveValue("Rifinisci questo task."); // shown again, ready
    expect(sent).not.toHaveBeenCalled();
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
