import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { ReferenceModal } from "./ReferencesSection";

afterEach(() => vi.unstubAllGlobals());

const SETTINGS = { base_url: "https://acme.atlassian.net", email: "me@acme.it", has_token: true, jira_project_key: "NAV", confluence_space_key: "DOC" };
const ISSUE = (key: string, summary: string) => ({
  key, summary, status: "In corso", issue_type: "Bug", priority: "Alta", assignee: "Ada", updated: null, description: "Ci mette **10 s**.",
  url: `https://acme.atlassian.net/browse/${key}`, related: [{ key: "NAV-8", summary: "Profilare", status: "Da fare", relation: "sotto-issue" }],
});

const renderModal = (onCreated = vi.fn(), onClose = vi.fn()) => {
  renderPage(<ReferenceModal project="acme" opened onClose={onClose} onCreated={onCreated} onDeleted={() => {}} />);
  return { onCreated, onClose };
};

describe("Nuovo riferimento from Jira or Confluence", () => {
  it("searches Jira in the default project (or everywhere), previews and copies an issue", async () => {
    const asked: string[] = [];
    const copied = vi.fn(async (request: Request) => ({ name: "context-reference-nav-7-login-lento.md", created: true, body: await request.json() }));
    mockApi({
      "GET /projects/acme/atlassian": SETTINGS,
      "GET /projects/acme/atlassian/favorites": [{ id: 1, kind: "jira_issue", ref: "NAV-1", title: "Vecchia", url: "x" }],
      "GET /projects/acme/atlassian/jira/search": (request: Request) => {
        asked.push(new URL(request.url).search);
        return [ISSUE("NAV-7", "Login lento"), ISSUE("NAV-9", "Logout lento")];
      },
      "POST /projects/acme/atlassian/jira/issues/NAV-7/reference": copied,
    });
    const { onCreated, onClose } = renderModal();

    fireEvent.click(await screen.findByRole("tab", { name: "Jira" }));
    expect(await screen.findByText("NAV-1")).toBeInTheDocument(); // a favorite
    fireEvent.change(screen.getByLabelText("Cerca su Jira"), { target: { value: "login" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    fireEvent.click(await screen.findByText("Login lento"));
    expect(await screen.findByText("NAV-7 · Login lento")).toBeInTheDocument();
    expect(screen.getByText(/Sotto-issue e collegate: NAV-8 \(sotto-issue\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copia e collega" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("context-reference-nav-7-login-lento.md"));
    expect(onClose).toHaveBeenCalled();
    expect((await copied.mock.results[0].value).body).toEqual({ link_to: [] }); // the window links it, as one written by hand
    expect(asked[0]).toBe("?q=login&jira_project=NAV");

    fireEvent.click(screen.getByLabelText(/Cerca ovunque/));
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    await waitFor(() => expect(asked[1]).toBe("?q=login"));
  });

  it("finds a Confluence page (one result opens at once) and copies it", async () => {
    const copied = vi.fn(() => ({ name: "context-reference-architettura.md", created: false }));
    mockApi({
      "GET /projects/acme/atlassian": SETTINGS,
      "GET /projects/acme/atlassian/favorites": [],
      "GET /projects/acme/atlassian/confluence/search": [{ id: "123", title: "Architettura", excerpt: "Monolite", url: "u" }],
      "GET /projects/acme/atlassian/confluence/pages/123": { id: "123", title: "Architettura", url: "https://acme.atlassian.net/wiki/123", body: "## Backend\nMonolite modulare." },
      "POST /projects/acme/atlassian/confluence/pages/123/reference": copied,
    });
    const { onCreated } = renderModal();

    fireEvent.click(await screen.findByRole("tab", { name: "Confluence" }));
    fireEvent.change(screen.getByLabelText("Cerca su Confluence"), { target: { value: "https://acme.atlassian.net/wiki/spaces/DOC/pages/123/Architettura" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    const preview = (await screen.findByText("Monolite modulare.")).closest(".mantine-Card-root") as HTMLElement;
    expect(within(preview).getByRole("heading", { name: "Backend" })).toBeInTheDocument();
    fireEvent.click(within(preview).getByRole("button", { name: "Copia e collega" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("context-reference-architettura.md"));
  });

  it("without Atlassian the window is the manual form only", async () => {
    mockApi({ "GET /projects/acme/atlassian": { base_url: "", email: "", has_token: false, jira_project_key: "", confluence_space_key: "" } });
    renderModal();

    expect(await screen.findByLabelText("Titolo")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Jira" })).not.toBeInTheDocument();
  });
});
