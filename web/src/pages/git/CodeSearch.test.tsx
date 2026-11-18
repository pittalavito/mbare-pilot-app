import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { GitTab } from "./GitTab";

afterEach(() => vi.unstubAllGlobals());

const RESULT = {
  matches: [
    { path: "api/Order.java", line: 3, text: "@Deprecated void old() {}" },
    { path: "api/Order.java", line: 9, text: "@Deprecated int x;" },
    { path: "web/app.ts", line: 1, text: "// @Deprecated" },
  ],
  total: 5, files: 2, truncated: true,
};

function open(extra: Record<string, unknown> = {}) {
  const bodies: unknown[] = [];
  const search = vi.fn(async (request: Request) => { bodies.push(await request.json()); return RESULT; });
  mockApi({
    "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }, { path: "web", name: "web" }],
    "GET /projects/acme/agent-tasks": [{ name: "agent-task-login.md", title: "Login", status: "todo", type: "development" }],
    "POST /projects/acme/code-search": search,
    ...extra,
  });
  renderPage(<Routes><Route path="/projects/:project/git" element={<GitTab />} /></Routes>, { route: "/projects/acme/git" });
  return bodies;
}

describe("Cerca nel codice", () => {
  it("searches with regex and filters, shows the results by file", async () => {
    const search = open();
    fireEvent.click(await screen.findByRole("tab", { name: /Cerca nel codice/ }));

    fireEvent.change(await screen.findByLabelText("Cerca"), { target: { value: "@Deprecated" } });
    fireEvent.click(screen.getByRole("switch", { name: "Regex" }));
    fireEvent.change(screen.getByLabelText("File"), { target: { value: "*.java" } });
    fireEvent.click(screen.getByRole("textbox", { name: "Repository" }));
    fireEvent.click(await screen.findByRole("option", { name: "api" }));
    fireEvent.click(screen.getByRole("button", { name: /Cerca$/ }));

    expect(await screen.findByText("api/Order.java")).toBeInTheDocument();
    expect(screen.getByText("web/app.ts")).toBeInTheDocument();
    expect(screen.getByText(/5 risultati in 2 file \(mostrati i primi 3/)).toBeInTheDocument();
    expect(search).toEqual([{ query: "@Deprecated", regex: true, files: "*.java", repository: "api" }]);
  });

  it("saves the search as a reference linked to a task", async () => {
    const saved = vi.fn(async (request: Request) => {
      expect(await request.json()).toMatchObject({ query: "Order", title: "Ordini", task: "agent-task-login.md" });
      return { note: "code-reference-ordini.md", created: true, total: 5 };
    });
    open({ "POST /projects/acme/code-search/reference": saved });
    fireEvent.click(await screen.findByRole("tab", { name: /Cerca nel codice/ }));
    fireEvent.change(await screen.findByLabelText("Cerca"), { target: { value: "Order" } });
    fireEvent.click(screen.getByRole("button", { name: /Cerca$/ }));

    const title = await screen.findByLabelText("Titolo del riferimento");
    expect(title).toHaveValue("Order");
    fireEvent.change(title, { target: { value: "Ordini" } });
    fireEvent.click(screen.getByRole("textbox", { name: "Collega a un task" }));
    fireEvent.click(await screen.findByRole("option", { name: "Login" }));
    fireEvent.click(screen.getByRole("button", { name: /Salva come riferimento/ }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await screen.findByRole("link", { name: "code-reference-ordini.md" })).toHaveAttribute("href", "/projects/acme/project?note=code-reference-ordini.md");
    expect(screen.getByText(/collegato al task/)).toBeInTheDocument();
  });

  it("says when nothing is found and when the regex is broken", async () => {
    open({ "POST /projects/acme/code-search": () => new Response(JSON.stringify({ detail: "Regex non valida: x" }), { status: 400 }) });
    fireEvent.click(await screen.findByRole("tab", { name: /Cerca nel codice/ }));
    fireEvent.change(await screen.findByLabelText("Cerca"), { target: { value: "(" } });
    fireEvent.click(screen.getByRole("button", { name: /Cerca$/ }));
    expect(await screen.findByText("Regex non valida: x")).toBeInTheDocument();
  });
});
