import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { NewActivityModal } from "./NewActivityModal";

afterEach(() => vi.unstubAllGlobals());

const REFERENCE = (name: string, title: string, kind = "context_reference") => ({
  name, title, kind, source: "", source_url: "", repository: "", path: "", content: "", linked_from: [],
});

function api(draft: unknown = { title: "Login con OTP", description: "L'OTP al login.", items: ["Analisi", "Sviluppo"], references: [], run_id: "r", cost_eur: 0.0012 }) {
  const drafted = vi.fn(async (request: Request) => { const body = await request.json(); return typeof draft === "function" ? draft(body) : draft; });
  const created = vi.fn(async (request: Request) => ({ ...(await request.json()), name: "attivita-login-con-otp.md" }));
  mockApi({
    "GET /projects/acme/references": [REFERENCE("context-reference-spec-login.md", "Spec login"), REFERENCE("code-reference-auth.md", "Auth", "code_reference")],
    "POST /projects/acme/context-index/search": [{ path: "context/arch.md", title: "Architettura", section: "Login", text: "Il login passa da auth.", score: 0.9 }],
    "POST /projects/acme/activities/draft": drafted,
    "POST /projects/acme/activities": created,
    "GET /projects/acme/atlassian": { base_url: "https://acme.atlassian.net", email: "x", has_token: true, jira_project_key: "NAV", confluence_space_key: "DOC" },
    "GET /projects/acme/atlassian/favorites": [],
    "GET /projects/acme/atlassian/jira/search": [{ key: "NAV-7", summary: "Login lento", status: "", issue_type: "", priority: "", assignee: "", updated: null, description: "", url: "u", related: [] }],
    "POST /projects/acme/atlassian/jira/issues/NAV-7/reference": { name: "context-reference-nav-7-login-lento.md", created: true },
  });
  return { drafted, created };
}

/** «➕ Nuova attività» on its second way, «📎 Parto da riferimenti». */
const render = (onCreated = vi.fn()) => {
  renderPage(<NewActivityModal project="acme" opened onClose={() => {}} onCreated={onCreated} />);
  fireEvent.click(screen.getByText("📎 Parto da riferimenti"));
  return onCreated;
};

describe("«➕ Nuova attività» · «📎 Parto da riferimenti»", () => {
  it("chooses references and context, gets the proposal, corrects it and creates the activity", async () => {
    const { drafted, created } = api();
    const onCreated = render();
    expect(screen.getByRole("button", { name: "✨ Proponi" })).toBeDisabled();

    fireEvent.click(await screen.findByLabelText(/Spec login/));
    fireEvent.click(screen.getByRole("tab", { name: "Contesto" }));
    fireEvent.change(screen.getByLabelText("Cerca nel contesto"), { target: { value: "login" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    fireEvent.click(await screen.findByLabelText("Architettura · Login"));
    fireEvent.click(screen.getByRole("button", { name: "✨ Proponi" }));

    const title = await screen.findByLabelText("Titolo");
    expect(drafted).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Voci della todo (una per riga)")).toHaveValue("Analisi\nSviluppo");
    fireEvent.change(title, { target: { value: "Login OTP" } });
    fireEvent.click(screen.getByRole("button", { name: "Crea attività" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ name: "attivita-login-con-otp.md" })));
    expect(await created.mock.results[0].value).toMatchObject({
      title: "Login OTP", status: "todo", references: ["context-reference-spec-login.md"],
      items: [{ text: "Analisi", done: false }, { text: "Sviluppo", done: false }],
    });
  });

  it("sends only names and titles, and a Jira issue copied becomes a chosen reference (removable)", async () => {
    const bodies: unknown[] = [];
    const { drafted } = api((body: unknown) => { bodies.push(body); return { title: "X", description: "", items: [], references: [], run_id: "r", cost_eur: 0 }; });
    render();

    fireEvent.click(await screen.findByRole("tab", { name: "Jira" }));
    fireEvent.change(await screen.findByLabelText("Cerca su Jira"), { target: { value: "login" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    fireEvent.click(await screen.findByRole("button", { name: "Copia e scegli" }));
    expect(await screen.findByText(/context-reference-nav-7-login-lento.md/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Riferimenti del progetto" }));
    fireEvent.click(await screen.findByLabelText(/Auth/));
    fireEvent.click(screen.getByRole("button", { name: "Togli code-reference-auth.md" }));
    fireEvent.click(screen.getByRole("button", { name: "✨ Proponi" }));

    await waitFor(() => expect(drafted).toHaveBeenCalled());
    await waitFor(() => expect(bodies[0]).toEqual({ references: ["context-reference-nav-7-login-lento.md"], context: [] }));
    fireEvent.click(await screen.findByRole("button", { name: "← Indietro" }));
    expect(screen.getByRole("button", { name: "✨ Proponi" })).toBeEnabled();
  });

  it("shows when the secretary does not answer", async () => {
    api();
    mockApi({
      "GET /projects/acme/references": [REFERENCE("context-reference-spec-login.md", "Spec login")],
      "POST /projects/acme/activities/draft": () => new Response(JSON.stringify({ detail: "Il Segretario non ha risposto: giù" }), { status: 502 }),
    });
    render();

    fireEvent.click(await screen.findByLabelText(/Spec login/));
    fireEvent.click(screen.getByRole("button", { name: "✨ Proponi" }));

    expect(await screen.findByText(/Il Segretario non ha risposto/)).toBeInTheDocument();
  });
});
