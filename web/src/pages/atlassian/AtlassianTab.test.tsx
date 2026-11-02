import { fireEvent, screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { AtlassianTab } from "./AtlassianTab";

afterEach(() => vi.unstubAllGlobals());

const SETTINGS = {
  base_url: "https://acme.atlassian.net", email: "ada@example.com", has_token: true,
  jira_project_key: "NAV", confluence_space_key: "DOC",
};

/** What the API sends: the rich text already as Markdown (domain/client/atlassian). */
const MARKDOWN = [
  "## Passi",
  "",
  "| Nome | Valore |",
  "| --- | --- |",
  "| timeout | 30 |",
  "",
  "```json",
  '{"id": 1}',
  "```",
].join("\n");

const ISSUE = {
  key: "NAV-7", summary: "Login lento", status: "Aperta", issue_type: "Bug", priority: "Alta", assignee: null,
  updated: null, url: "https://acme.atlassian.net/browse/NAV-7", description: MARKDOWN,
};

const PAGE = { id: "42", title: "Setup", url: "https://acme.atlassian.net/wiki/spaces/DOC/pages/42", body: MARKDOWN };

function renderTab() {
  mockApi({
    "GET /projects/acme/atlassian": SETTINGS,
    "GET /projects/acme/atlassian/favorites": [],
    "GET /projects/acme/atlassian/jira/issues/NAV-7": ISSUE,
    "GET /projects/acme/atlassian/confluence/pages": [{ id: "42", title: "Setup", space_id: "7", url: PAGE.url, body: "" }],
    "GET /projects/acme/atlassian/confluence/pages/42": PAGE,
  });
  return renderPage(
    <Routes><Route path="/projects/:project/atlassian" element={<AtlassianTab />} /></Routes>,
    { route: "/projects/acme/atlassian" },
  );
}

/** The Markdown is drawn: a real table, a code block, a heading (not the raw text). */
async function expectRendered(card: HTMLElement) {
  const table = await within(card).findByRole("table");
  expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Nome", "Valore"]);
  expect(within(table).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["timeout", "30"]);
  expect(within(card).getByRole("heading", { name: "Passi" })).toBeTruthy();
  expect(card.querySelector("pre code")?.textContent).toBe('{"id": 1}\n');
  expect(within(card).queryByText(/\| --- \|/)).toBeNull();
}

describe("AtlassianTab", () => {
  it("draws a Jira description as Markdown", async () => {
    renderTab();

    fireEvent.change(await screen.findByLabelText("Chiave della issue"), { target: { value: "NAV-7" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));

    const title = await screen.findByText(/Login lento/);
    await expectRendered(title.closest(".mantine-Card-root") as HTMLElement);
  });

  it("draws a Confluence page as Markdown", async () => {
    renderTab();

    fireEvent.click(await screen.findByRole("tab", { name: "Confluence" }));
    fireEvent.click(await screen.findByRole("button", { name: /Pagine dello spazio DOC/ }));
    fireEvent.click(await screen.findByText("Setup"));

    const link = await screen.findByRole("link", { name: "Setup" });
    await expectRendered(link.closest(".mantine-Card-root") as HTMLElement);
  });
});
