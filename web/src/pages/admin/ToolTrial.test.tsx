import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { ToolTrial } from "./ToolTrial";

/** Admin → Tool: a tool tried by hand on a project; the ones that change something ask first. */

afterEach(() => vi.unstubAllGlobals());

const SPECS = [
  { name: "git_status", description: "Lo stato", writes: false, chatbot_only: false,
    args: [{ name: "repository", type: "str", default: null, description: "Il repository", required: true }] },
  { name: "save_note", description: "Salva una nota", writes: true, chatbot_only: false,
    args: [{ name: "title", type: "str", default: "Automation {date} {time}", description: null, required: false },
           { name: "content", type: "str", default: null, description: null, required: true }] },
  { name: "today", description: "Oggi", writes: false, chatbot_only: true, args: [] },
];

function api(tried: (request: Request) => unknown) {
  mockApi({
    "GET /tool-specs": SPECS,
    "GET /projects": [{ name: "acme", description: "", source: "folder", root_path: "/c", embedding_model: "", created_at: "2026-11-16T10:00:00Z",
                        folder_exists: true }],
    "POST /tools/git_status/try": tried,
    "POST /tools/save_note/try": tried,
  });
}

async function choose(label: string, option: string) {
  fireEvent.click(await screen.findByRole("textbox", { name: label }));
  fireEvent.click(await screen.findByRole("option", { name: option }));
}

describe("Admin → Tool", () => {
  it("tries a tool that reads at once and shows the text and the JSON", async () => {
    const bodies: unknown[] = [];
    api(async (request) => { bodies.push(await request.json()); return { ok: true, text: "Repository api · branch main", result: { text: "x" }, error: null }; });
    renderPage(<ToolTrial />);
    await choose("Tool", "git_status");
    await choose("Progetto", "acme");
    fireEvent.change(screen.getByLabelText("repository"), { target: { value: "api" } });
    fireEvent.click(screen.getByRole("button", { name: /Prova/ }));

    expect(await screen.findByText("Repository api · branch main")).toBeInTheDocument();
    expect(bodies).toEqual([{ project: "acme", args: { repository: "api" } }]);
    expect(within(screen.getByTestId("tool-result")).getByText(/"text": "x"/)).toBeInTheDocument();
  });

  it("a tool that changes something asks first; an error is shown", async () => {
    const tried = vi.fn(() => ({ ok: false, text: "", result: { error: "vuoto" }, error: "Niente da salvare: il testo è vuoto." }));
    api(tried);
    renderPage(<ToolTrial />);
    await choose("Tool", "save_note ✏️");
    expect(screen.getByText("cambia qualcosa")).toBeInTheDocument();
    await choose("Progetto", "acme");
    fireEvent.click(screen.getByRole("button", { name: /Prova/ }));
    expect(tried).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Procedi" }));

    await waitFor(() => expect(tried).toHaveBeenCalled());
    expect(await screen.findByText("Niente da salvare: il testo è vuoto.")).toBeInTheDocument();
  });

  it("a chat-only tool says so and one without arguments says that too", async () => {
    api(() => ({ ok: true, text: "", result: {}, error: null }));
    renderPage(<ToolTrial />);
    await choose("Tool", "today (solo chat)");
    expect(screen.getByText("pensato per una chat")).toBeInTheDocument();
    expect(screen.getByText("Nessun argomento.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Prova/ })).toBeDisabled(); // no project yet
  });
});
