import { createEvent, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { RoadmapPage } from "./RoadmapPage";

afterEach(() => vi.unstubAllGlobals());

const CARD = (id: string, title: string, extra = {}) => ({
  id, title, description: "", kind: "", priority: null, owner: "", status: "todo", feasibility: "", ...extra,
});
const BOARD = {
  goal: "Uso in Aitho", vision: "Le modifiche future dell'app.",
  items: [
    CARD("uso-quotidiano", "Uso quotidiano", { description: "Ogni giorno", kind: "uso", owner: "tu", status: "in_progress" }),
    CARD("integrazione", "Integrazione Bitbucket", { kind: "integrazione", owner: "agente remoto", feasibility: "Fattibilità già verificata." }),
    CARD("bug-login", "Bug del login", { kind: "bug", priority: "high", owner: "claude" }),
    CARD("piano-29", "Piano 29", { kind: "rag", status: "done" }),
  ],
};

function api(extra: Record<string, unknown> = {}) {
  const sent: Record<string, unknown[]> = {};
  const record = (key: string) => async (request: Request) => {
    (sent[key] ??= []).push(request.method === "DELETE" ? null : await request.json());
    return BOARD;
  };
  mockApi({
    "GET /roadmap": BOARD,
    "POST /roadmap/items": record("add"),
    "PUT /roadmap/items/bug-login": record("update"),
    "POST /roadmap/items/bug-login/move": record("move"),
    "DELETE /roadmap/items/bug-login": record("delete"),
    "PUT /roadmap/header": record("header"),
    ...extra,
  });
  return sent;
}

describe("«🚀 Mbare Pilot»", () => {
  it("shows the header and the board by status, the high priority first", async () => {
    api();
    renderPage(<RoadmapPage />);

    expect(await screen.findByText("🎯 Uso in Aitho")).toBeInTheDocument();
    expect(screen.getByText("3 aperte")).toBeInTheDocument();
    expect(within(screen.getByTestId("column-in_progress")).getByText("Uso quotidiano")).toBeInTheDocument();
    const todo = within(screen.getByTestId("column-todo"));
    expect(todo.getAllByText(/Bug del login|Integrazione Bitbucket/).map((node) => node.textContent)).toEqual(["Bug del login", "Integrazione Bitbucket"]);
    expect(todo.getByText("✓ Fattibilità già verificata.")).toBeInTheDocument();
    expect(todo.getByText("🛰 agente remoto")).toBeInTheDocument();
    expect(todo.getByText("alta")).toBeInTheDocument();
    expect(within(screen.getByTestId("column-done")).getByText("🧠 RAG")).toBeInTheDocument();
  });

  it("creates a card", async () => {
    const sent = api();
    renderPage(<RoadmapPage />);

    fireEvent.click(await screen.findByRole("button", { name: "➕ Nuova scheda" }));
    fireEvent.change(await screen.findByLabelText("Titolo"), { target: { value: " Esporta in PDF " } });
    fireEvent.click(screen.getByRole("button", { name: "Crea" }));

    await waitFor(() => expect(sent.add).toHaveLength(1));
    expect(sent.add[0]).toMatchObject({ title: "Esporta in PDF", status: "todo", priority: null });
  });

  it("changes and deletes a card", async () => {
    const sent = api();
    renderPage(<RoadmapPage />);

    fireEvent.click(await screen.findByText("Bug del login"));
    const title = await screen.findByLabelText("Titolo");
    expect(title).toHaveValue("Bug del login");
    fireEvent.change(title, { target: { value: "Bug del login su Windows" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(sent.update).toHaveLength(1));
    expect(sent.update[0]).toMatchObject({ title: "Bug del login su Windows", kind: "bug", priority: "high", owner: "claude" });
    expect(sent.update[0]).not.toHaveProperty("id");

    fireEvent.click(await screen.findByText("Bug del login"));
    fireEvent.click(await screen.findByRole("button", { name: "Elimina" }));
    fireEvent.click(await screen.findByRole("button", { name: "Sì, elimina" }));
    await waitFor(() => expect(sent.delete).toHaveLength(1));
  });

  it("moves a card by dragging it or with «Sposta»", async () => {
    const sent = api();
    renderPage(<RoadmapPage />);

    const card = await screen.findByTestId("card-bug-login");
    const data = new Map<string, string>();
    const dataTransfer = { setData: (type: string, value: string) => data.set(type, value), getData: (type: string) => data.get(type) ?? "", effectAllowed: "" };
    fireEvent(card, Object.assign(createEvent.dragStart(card), { dataTransfer }));
    const column = screen.getByTestId("column-in_progress");
    fireEvent(column, Object.assign(createEvent.dragOver(column), { dataTransfer }));
    fireEvent(column, Object.assign(createEvent.drop(column), { dataTransfer }));
    await waitFor(() => expect(sent.move).toHaveLength(1));
    expect(sent.move[0]).toEqual({ status: "in_progress" });

    fireEvent.click(screen.getByRole("button", { name: "Sposta Bug del login" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Fatto" }));
    await waitFor(() => expect(sent.move).toHaveLength(2));
    expect(sent.move[1]).toEqual({ status: "done" });
  });

  it("changes goal and vision", async () => {
    const sent = api();
    renderPage(<RoadmapPage />);

    fireEvent.click(await screen.findByRole("button", { name: "✏️ Modifica" }));
    fireEvent.change(await screen.findByLabelText("Traguardo"), { target: { value: "Strumento di Aitho" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(sent.header).toEqual([{ goal: "Strumento di Aitho", vision: "Le modifiche future dell'app." }]));
  });

  it("without cards says how to make one", async () => {
    api({ "GET /roadmap": { goal: "", vision: "", items: [] } });
    renderPage(<RoadmapPage />);
    expect(await screen.findByText(/creane una con «➕ Nuova scheda»/)).toBeInTheDocument();
  });
});
