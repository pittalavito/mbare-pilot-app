import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";

afterEach(() => vi.unstubAllGlobals());

const DOCS = [{ name: "architettura.md", kind: "note", size: 1, modified_at: "2026-11-10T10:00:00Z" }];
const INDEX = { documents: 1, pieces: 3, embedder: "hashing-512", error: null };
const HIT = { path: "context/architettura.md", title: "Architettura", section: "Database", text: "PostgreSQL con Flyway.", score: 0.83 };

const renderData = () =>
  renderPage(<Routes>{zoneRoutes()}</Routes>, { route: "/projects/acme/project" });

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

  it("shows the general context read only and where each hit comes from", async () => {
    mockApi({
      "GET /projects/acme/notes": [],
      "GET /projects/acme/wip": { content: "", pending_words: 0 },
      "GET /projects/acme/context": [],
      "GET /projects/acme/context-general": [{ name: "giro.md", title: "Il giro", content: "# Il giro\n\nSi avvia con Avvia." }],
      "GET /projects/acme/context-index": { ...INDEX, documents: 2, general: 1 },
      "POST /projects/acme/context-index/search": [{ ...HIT, path: "general/giro.md", title: "Il giro", section: "", origin: "generale" }],
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Contesto/ }));
    expect(await screen.findByText(/di cui 1 generali/)).toBeInTheDocument();
    fireEvent.click(await screen.findByText("Il giro"));
    expect(await screen.findByLabelText("Documento generale")).toHaveValue("# Il giro\n\nSi avvia con Avvia.");
    expect(screen.getByLabelText("Documento generale")).toHaveAttribute("readonly");
    fireEvent.change(screen.getByLabelText("Prova una ricerca"), { target: { value: "giro" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    expect(await screen.findByText("generale")).toBeInTheDocument();
  });

  it("creates the ready documents and generates the repository map", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: "glossario.md", index_error: null, body: await request.json() }));
    const generated = vi.fn(() => ({ name: "repository.md", index_error: null }));
    mockApi({
      "GET /projects/acme/notes": [],
      "GET /projects/acme/wip": { content: "", pending_words: 0 },
      "GET /projects/acme/context": [{ name: "convenzioni.md", kind: "note", size: 1, modified_at: "2026-11-10T10:00:00Z" }],
      "GET /projects/acme/context/convenzioni.md": { name: "convenzioni.md", content: "# Convenzioni\n" },
      "GET /projects/acme/context/glossario.md": { name: "glossario.md", content: "# Glossario\n" },
      "GET /projects/acme/context/repository.md": { name: "repository.md", content: "# Repository\n" },
      "PUT /projects/acme/context/glossario.md": saved,
      "POST /projects/acme/context/repository-map": generated,
      "GET /projects/acme/context-general": [],
      "GET /projects/acme/context-index": INDEX,
    });
    renderData();

    fireEvent.click(await screen.findByRole("tab", { name: /Contesto/ }));
    expect(await screen.findByRole("button", { name: /Decisioni \(modello\)/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Convenzioni \(modello\)/ })).not.toBeInTheDocument(); // already there
    fireEvent.click(screen.getByRole("button", { name: /Glossario \(modello\)/ }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect((await saved.mock.results[0].value).body.content).toContain("# Glossario");

    fireEvent.click(screen.getByRole("button", { name: /Genera mappa dei repository/ }));
    await waitFor(() => expect(generated).toHaveBeenCalled());
  });
});
