import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { DataTab } from "./DataTab";

afterEach(() => vi.unstubAllGlobals());

const NOTES = [{ name: "decisioni.md", kind: "note", size: 1, modified_at: "2026-10-25T10:00:00Z", note_type: "generic" }];
const TEXT = "Oggi: 2026-11-10 (martedì)\n\nTesto nuovo della WIP:\nsentire PERSONA_1 e Giulia, scrivere a MAIL_1";
const PREVIEW = {
  text: TEXT, words: 7, paragraphs: 1, processing: 1, over_limit: false,
  spans: [
    { start: TEXT.indexOf("PERSONA_1"), end: TEXT.indexOf("PERSONA_1") + 9, alias: "PERSONA_1", origin: "tag" },
    { start: TEXT.indexOf("MAIL_1"), end: TEXT.indexOf("MAIL_1") + 6, alias: "MAIL_1", origin: "auto" },
  ],
};
const PROPOSALS = {
  run_id: "r1",
  proposals: [
    { id: 1, kind: "new_activity", source: "sentire Marco", title: "Log da Marco", description: "", items: ["Chiedere i log"], activity: "",
      activity_title: "", text: "", item: 0, item_text: "", priority: null, due: null },
    { id: 2, kind: "check_item", source: "tag fatto", activity: "attivita-rilascio.md", activity_title: "Rilascio", item: 2,
      item_text: "Taggare il commit", title: "", description: "", items: [], text: "", priority: null, due: null },
    { id: 3, kind: "set_item", source: "entro venerdì", activity: "attivita-rilascio.md", activity_title: "Rilascio", item: 3,
      item_text: "Note", title: "", description: "", items: [], text: "", priority: "high", due: "2026-11-13" },
  ],
};

const renderData = () =>
  renderPage(<Routes><Route path="/projects/:project/data" element={<DataTab />} /></Routes>, { route: "/projects/acme/data" });

describe("the WIP note", () => {
  it("comes first, even before it exists, and can be processed only with new saved text", async () => {
    mockApi({ "GET /projects/acme/notes": NOTES, "GET /projects/acme/wip": { content: "", pending_words: 0 } });
    renderData();

    expect(await screen.findByPlaceholderText(/Scrivi di getto/)).toHaveValue("");
    expect(screen.getByRole("button", { name: /Elabora WIP/ })).toBeDisabled(); // nothing new
    expect(screen.queryByRole("button", { name: "Elimina" })).not.toBeInTheDocument();
  });

  it("previews the masked text, masks a word by hand, then applies the chosen proposals", async () => {
    let previews = 0;
    const preview = vi.fn(() => { previews += 1; return PREVIEW; });
    const masked = vi.fn(async (request: Request) => ({ alias: "PERSONA_2", ...(await request.json()) }));
    const applied = vi.fn(async (request: Request) => ({ body: await request.json(), applied: ["Nuova attività «Log dai sistemisti»"], skipped: ["Voce 2 di «Rilascio»: la voce è già fatta"] }));
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/wip": { content: "sentire mask{Marco}", pending_words: 2 },
      "GET /projects/acme/activities": [{ name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", items: [] }],
      "POST /projects/acme/wip/preview": preview,
      "POST /projects/acme/masking": masked,
      "POST /projects/acme/wip/process": PROPOSALS,
      "POST /projects/acme/wip/apply": applied,
    });
    renderData();

    fireEvent.click(await screen.findByRole("button", { name: /Elabora WIP \(2 parole nuove\)/ }));
    const dialog = await screen.findByRole("dialog");
    const box = await within(dialog).findByTestId("wip-preview");
    expect(within(box).getByText("PERSONA_1")).toHaveAttribute("title", "mask{}");
    expect(within(box).getByText("MAIL_1")).toHaveAttribute("title", "riconosciuto (solo per questa volta)");

    fireEvent.click(within(box).getByText("Giulia"));
    fireEvent.click(within(dialog).getByRole("button", { name: /Persona/ }));
    await waitFor(() => expect(masked).toHaveBeenCalled());
    expect(await masked.mock.results[0].value).toMatchObject({ category: "person", value: "Giulia" });
    await waitFor(() => expect(previews).toBe(2)); // shown again, with the new alias

    fireEvent.click(within(dialog).getByRole("button", { name: /Invia al segretario/ }));
    expect(await within(dialog).findByText("«sentire Marco»")).toBeInTheDocument();
    expect(within(dialog).getByText(/priorità alta, scadenza 13\/11\/2026/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Titolo"), { target: { value: "Log dai sistemisti" } });
    fireEvent.click(within(dialog).getByLabelText("Scegli la proposta 3"));
    fireEvent.click(within(dialog).getByRole("button", { name: "✅ Applica (2)" }));

    await waitFor(() => expect(applied).toHaveBeenCalled());
    const { body } = await applied.mock.results[0].value;
    expect(body.run_id).toBe("r1");
    expect(body.choices.map((choice: { proposal: { id: number }; edited: boolean }) => [choice.proposal.id, choice.edited])).toEqual([[1, true], [2, false]]);
    expect(body.choices[0].proposal.title).toBe("Log dai sistemisti");
    expect(await within(dialog).findByText("Nuova attività «Log dai sistemisti»")).toBeInTheDocument();
    expect(within(dialog).getByText(/la voce è già fatta/)).toBeInTheDocument();
  });

  it("a long WIP can be processed a few paragraphs at a time", async () => {
    const bodies: unknown[] = [];
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/wip": { content: "molto testo", pending_words: 2500 },
      "POST /projects/acme/wip/preview": async (request: Request) => {
        bodies.push(await request.json());
        return { ...PREVIEW, paragraphs: 3, over_limit: true };
      },
    });
    renderData();

    fireEvent.click(await screen.findByRole("button", { name: /Elabora WIP/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByLabelText("Paragrafi da elaborare"));
    fireEvent.click(await screen.findByRole("option", { name: "I primi 2" }));

    await waitFor(() => expect(bodies).toEqual([{ paragraphs: null }, { paragraphs: 2 }]));
  });

  it("without proposals nothing is applied", async () => {
    mockApi({
      "GET /projects/acme/notes": NOTES,
      "GET /projects/acme/wip": { content: "niente", pending_words: 1 },
      "POST /projects/acme/wip/preview": PREVIEW,
      "POST /projects/acme/wip/process": { run_id: "r2", proposals: [] },
    });
    renderData();

    fireEvent.click(await screen.findByRole("button", { name: /Elabora WIP/ }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByTestId("wip-preview");
    fireEvent.click(within(dialog).getByRole("button", { name: /Invia al segretario/ }));
    expect(await within(dialog).findByText(/non ha proposte: la WIP resta da elaborare/)).toBeInTheDocument();
  });
});
