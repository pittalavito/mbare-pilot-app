import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { CodeSearch } from "./CodeSearch";
import { FromCodeSearch, SavedSearchesSettings } from "./SavedSearches";

afterEach(() => vi.unstubAllGlobals());

const SAVED = [
  { name: "TODO", query: "\\bTODO\\b", regex: true, files: "", description: "I TODO", origin: "app" },
  { name: "Commenti MBARE", query: "//\\s*MBARE", regex: true, files: "*.java", description: "", origin: "progetto" },
];
const RESULT = { matches: [{ path: "api/A.java", line: 4, text: "// MBARE login" }], total: 1, files: 1, truncated: false };
const PROPOSAL = { regex: "//\\s*MBARE", explanation: "I commenti MBARE.", example: "// MBARE x", valid: true, example_matches: true, run_id: "r", cost_eur: 0.0001 };

function api(extra: Record<string, unknown> = {}) {
  const bodies: Record<string, unknown[]> = { search: [], saved: [], regex: [], reference: [] };
  const record = (name: string, answer: unknown) => async (request: Request) => { bodies[name].push(await request.json()); return answer; };
  mockApi({
    "GET /projects/acme/code-search/saved": SAVED,
    "PUT /projects/acme/code-search/saved": record("saved", SAVED),
    "DELETE /projects/acme/code-search/saved/Commenti MBARE": [SAVED[0]],
    "POST /projects/acme/code-search/regex": record("regex", PROPOSAL),
    "POST /projects/acme/code-search": record("search", RESULT),
    "POST /projects/acme/code-search/reference": record("reference", { note: "code-reference-commenti-mbare.md", created: true, total: 1 }),
    "GET /projects/acme/git/repositories": [],
    "GET /projects/acme/agent-tasks": [],
    ...extra,
  });
  return bodies;
}

const pick = async (name: string) => {
  fireEvent.click(await screen.findByRole("textbox", { name: "⭐ Ricerche salvate" }));
  fireEvent.click(await screen.findByRole("option", { name: new RegExp(name) }));
};

describe("Ricerche salvate", () => {
  it("in «Cerca nel codice» a saved search fills the search, «⭐ Salva ricerca» names it", async () => {
    const bodies = api();
    renderPage(<CodeSearch project="acme" />);

    await pick("Commenti MBARE");
    expect(screen.getByLabelText("Cerca")).toHaveValue("//\\s*MBARE");
    expect(screen.getByLabelText("File")).toHaveValue("*.java");
    fireEvent.click(screen.getByRole("button", { name: "🔎 Cerca" }));
    await waitFor(() => expect(bodies.search[0]).toMatchObject({ query: "//\\s*MBARE", regex: true, files: "*.java" }));

    fireEvent.click(screen.getByRole("button", { name: "⭐ Salva ricerca" }));
    fireEvent.change(await screen.findByLabelText("Nome"), { target: { value: "Mie" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(bodies.saved[0]).toEqual({ name: "Mie", query: "//\\s*MBARE", regex: true, files: "*.java", description: "", replacing: "" }));
  });

  it("«✨ Regex» asks the agent and «Usa» puts the regex in the search", async () => {
    const bodies = api();
    renderPage(<CodeSearch project="acme" />);

    fireEvent.click(await screen.findByRole("button", { name: "✨ Regex" }));
    fireEvent.change(await screen.findByLabelText("Cosa vuoi cercare"), { target: { value: "i commenti MBARE" } });
    fireEvent.click(screen.getByRole("button", { name: "✨ Proponi" }));

    expect(await screen.findByText("trova il suo esempio")).toBeInTheDocument();
    expect(bodies.regex[0]).toEqual({ description: "i commenti MBARE" });
    fireEvent.click(screen.getByRole("button", { name: "Usa" }));
    await waitFor(() => expect(screen.getByLabelText("Cerca")).toHaveValue("//\\s*MBARE"));
    expect(screen.getByRole("switch", { name: "Regex" })).toBeChecked();
  });

  it("a regex that does not work is said and cannot be used", async () => {
    api({ "POST /projects/acme/code-search/regex": { ...PROPOSAL, valid: false, example_matches: false } });
    renderPage(<CodeSearch project="acme" />);

    fireEvent.click(await screen.findByRole("button", { name: "✨ Regex" }));
    fireEvent.change(await screen.findByLabelText("Cosa vuoi cercare"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "✨ Proponi" }));

    expect(await screen.findByText("regex non valida")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Usa" })).toBeDisabled();
  });

  it("in the settings: the app's and the project's, edit (an app one gets a project version) and delete", async () => {
    const bodies = api();
    renderPage(<SavedSearchesSettings project="acme" />);

    expect(await screen.findByText("dell'app")).toBeInTheDocument();
    expect(screen.getByText("del progetto")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Elimina" })).toHaveLength(1); // only the project's

    fireEvent.click(screen.getAllByRole("button", { name: "Modifica" })[0]);
    fireEvent.change(await screen.findByLabelText("Cerca"), { target: { value: "TODO|todo" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(bodies.saved[0]).toMatchObject({ name: "TODO", query: "TODO|todo", replacing: "" }));

    fireEvent.click(screen.getAllByRole("button", { name: "Modifica" })[1]);
    fireEvent.change(await screen.findByLabelText("Nome"), { target: { value: "MBARE" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(bodies.saved[1]).toMatchObject({ name: "MBARE", replacing: "Commenti MBARE" }));

    fireEvent.click(screen.getByRole("button", { name: "Elimina" }));
    fireEvent.click(await screen.findByRole("button", { name: "Sì, elimina" }));
    await waitFor(() => expect(screen.queryByText("del progetto")).not.toBeInTheDocument());
  });

  it("«🔎 Da codice»: a saved search becomes a code reference", async () => {
    const bodies = api();
    const onCreated = vi.fn();
    renderPage(<FromCodeSearch project="acme" createLabel="Crea e collega" onCreated={onCreated} />);

    await pick("Commenti MBARE");
    expect(screen.getByLabelText("Titolo del riferimento")).toHaveValue("Commenti MBARE");
    fireEvent.click(screen.getByRole("button", { name: "🔎 Prova" }));
    expect(await screen.findByText("1 risultato in 1 file")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Crea e collega" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("code-reference-commenti-mbare.md"));
    expect(bodies.reference[0]).toEqual({ query: "//\\s*MBARE", regex: true, files: "*.java", repository: "", title: "Commenti MBARE", task: "" });
  });
});
