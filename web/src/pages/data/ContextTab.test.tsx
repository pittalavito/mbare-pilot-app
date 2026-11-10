import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "./DataTab";

afterEach(() => vi.unstubAllGlobals());

const DOCS = [{ name: "architettura.md", kind: "note", size: 1, modified_at: "2026-11-10T10:00:00Z" }];
const INDEX = { documents: 1, pieces: 3, embedder: "hashing-512", error: null };
const HIT = { path: "context/architettura.md", title: "Architettura", section: "Database", text: "PostgreSQL con Flyway.", score: 0.83 };

const renderData = () =>
  renderPage(<Routes><Route path="/projects/:project/data" element={<DataTab />} /></Routes>, { route: "/projects/acme/data" });

describe("the Contesto tab", () => {
  it("shows the index, edits a document (saving indexes it), reindexes and tries a search", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: "architettura.md", index_error: null, body: await request.json() }));
    const searched = vi.fn(async (request: Request) => { await request.json(); return [HIT]; });
    const reindexed = vi.fn(() => ({ ...INDEX, documents: 2 }));
    mockApi({
      "GET /projects/acme/notes": [],
      "GET /projects/acme/wip": { content: "", pending_words: 0 },
      "GET /projects/acme/context": DOCS,
      "GET /projects/acme/context/architettura.md": { name: "architettura.md", content: "# Architettura\n" },
      "PUT /projects/acme/context/architettura.md": saved,
      "GET /projects/acme/context-index": INDEX,
      "POST /projects/acme/context-index/reindex": reindexed,
      "POST /projects/acme/context-index/search": searched,
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Contesto/ }));
    expect(await screen.findByText(/hashing-512/)).toBeInTheDocument();
    const editor = await screen.findByLabelText("Testo del documento");
    fireEvent.change(editor, { target: { value: "# Architettura\n\n## Database\nPostgreSQL con Flyway." } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect((await saved.mock.results[0].value).body).toEqual({ content: "# Architettura\n\n## Database\nPostgreSQL con Flyway." });

    fireEvent.change(screen.getByLabelText("Prova una ricerca"), { target: { value: "dove sono le migrazioni?" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    expect(await screen.findByText("Architettura › Database")).toBeInTheDocument();
    expect(screen.getByText("0.83")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Reindicizza tutto/ }));
    await waitFor(() => expect(reindexed).toHaveBeenCalled());
  });

  it("creates a document and says when the index cannot be built", async () => {
    const created = vi.fn(async (request: Request) => ({ name: "glossario.md", index_error: null, body: await request.json() }));
    mockApi({
      "GET /projects/acme/notes": [],
      "GET /projects/acme/wip": { content: "", pending_words: 0 },
      "GET /projects/acme/context": [],
      "GET /projects/acme/context-index": { documents: 0, pieces: 0, embedder: "", error: "OPENROUTER_API_KEY is not set" },
      "PUT /projects/acme/context/glossario": created,
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Contesto/ }));
    expect(await screen.findByText("OPENROUTER_API_KEY is not set")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Nuovo documento/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Nome"), { target: { value: "glossario" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crea" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect((await created.mock.results[0].value).body.content).toBe("# glossario\n\n## \n");
  });
});
