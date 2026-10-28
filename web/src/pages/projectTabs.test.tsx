import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentsSection } from "../components/agents/AgentsSection";
import { mockApi, renderPage } from "../test/render";
import { AtlassianTab } from "./atlassian/AtlassianTab";
import { DataTab } from "./data/DataTab";
import { GitTab } from "./git/GitTab";
import { SettingsTab } from "./settings/SettingsTab";

/** The tabs Dati, Git, Atlassian and Impostazioni of a project, and the agents section (shared with the Library). */

afterEach(() => vi.unstubAllGlobals());

const inProject = (path: string, ui: React.ReactElement) =>
  renderPage(<Routes><Route path={`/projects/:project/${path}`} element={ui} /><Route path="/projects" element={<div>lista progetti</div>} /></Routes>, {
    route: `/projects/acme/${path}`,
  });

const json = async (request: Request) => request.json();

describe("DataTab", () => {
  it("opens the first note and saves the edited text", async () => {
    const saved = vi.fn(async (request: Request) => ({ name: "idee.md", kind: "note", size: 9, modified_at: "2026-10-25T10:00:00Z", ...(await json(request)) }));
    mockApi({
      "GET /projects/acme/notes": [{ name: "idee.md", kind: "note", size: 8, modified_at: "2026-10-25T10:00:00Z" }],
      "GET /projects/acme/notes/idee.md": { name: "idee.md", content: "# Idee\n" },
      "PUT /projects/acme/notes/idee.md": saved,
    });
    inProject("data", <DataTab />);

    const editor = await screen.findByDisplayValue(/# Idee/);
    expect(screen.getByRole("button", { name: "Salva" })).toBeDisabled(); // nothing changed yet
    fireEvent.change(editor, { target: { value: "# Idee\n- una" } });
    expect(screen.getByText(/modifiche non salvate/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ content: "# Idee\n- una" });
  });
});

describe("GitTab", () => {
  it("searches the commits of the chosen repository with the filters", async () => {
    let query = "";
    mockApi({
      "GET /projects/acme/git/repositories": [{ path: "api", name: "api" }],
      "GET /projects/acme/git/log": (request: Request) => {
        query = new URL(request.url).search;
        return [{ hash: "abc1234def", short_hash: "abc1234", author: "Ada", email: "ada@x.it", date: "2026-10-25T10:00:00Z", subject: "Fix login" }];
      },
    });
    inProject("git", <GitTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Cerca commit" }));
    expect(await screen.findByText("Scegli un repository.")).toBeInTheDocument();

    fireEvent.click(screen.getByPlaceholderText("Scegli un repository"));
    fireEvent.click(await screen.findByRole("option", { name: "api" }));
    fireEvent.change(screen.getByLabelText("Autore"), { target: { value: "Ada" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca commit" }));

    expect(await screen.findByText("Fix login")).toBeInTheDocument();
    expect(query).toContain("path=api");
    expect(query).toContain("author=Ada");
  });
});

describe("AtlassianTab", () => {
  it("opens an issue by key and adds it to the favorites", async () => {
    const added = vi.fn(json);
    mockApi({
      "GET /projects/acme/atlassian": { base_url: "https://acme.atlassian.net", email: "a@b.it", has_token: true, jira_project_key: "NAV", confluence_space_key: "" },
      "GET /projects/acme/atlassian/favorites": [],
      "GET /projects/acme/atlassian/jira/issues/NAV-7": {
        key: "NAV-7", summary: "Porto bloccato", status: "In corso", issue_type: "Bug", priority: null, assignee: null, updated: null,
        description: "Dettagli", url: "https://acme.atlassian.net/browse/NAV-7",
      },
      "POST /projects/acme/atlassian/favorites": added,
    });
    inProject("atlassian", <AtlassianTab />);

    fireEvent.change(await screen.findByPlaceholderText("NAV-123"), { target: { value: "NAV-7" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));
    expect(await screen.findByText(/Porto bloccato/)).toBeInTheDocument();
    fireEvent.click(screen.getByTitle("Aggiungi ai preferiti"));

    await waitFor(() => expect(added).toHaveBeenCalled());
    expect(await added.mock.results[0].value).toEqual({ kind: "jira_issue", ref: "NAV-7", title: "Porto bloccato", url: "https://acme.atlassian.net/browse/NAV-7" });
  });
});

describe("SettingsTab", () => {
  const PROJECT = {
    name: "acme", description: "", source: "scratch", root_path: "/code/acme", embedding_model: "openai/text-embedding-3-small",
    created_at: "2026-10-25T10:00:00Z", folder_exists: true,
  };

  it("previews the definitions, syncs only the chosen ones and shows the report", async () => {
    const synced = vi.fn(async (request: Request) => {
      expect(await request.json()).toEqual({ only: [{ kind: "chatbot", file: "global-chat-bot.yml", name: "Bot" }] });
      return { project_name: "acme", items: [{ kind: "chatbot", file: "global-chat-bot.yml", name: "Bot", outcome: "updated", message: "" }] };
    });
    mockApi({
      "GET /projects/acme": PROJECT,
      "GET /projects/acme/definitions": [
        { kind: "agent", file: "global-agent.yml", name: "hello", state: "new", message: "" },
        { kind: "chatbot", file: "global-chat-bot.yml", name: "Bot", state: "exists", message: "" },
        { kind: "automation", file: "project/acme/automation.yml", name: null, state: "error", message: "steps: campo obbligatorio" },
      ],
      "POST /projects/acme/definitions/sync": synced,
    });
    inProject("settings", <SettingsTab />);

    fireEvent.click(await screen.findByRole("button", { name: /Definizioni da file/ }));
    expect(await screen.findByText("steps: campo obbligatorio")).toBeInTheDocument();
    expect(screen.getByText("esiste: il file vince")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Sincronizza project/acme/automation.yml" })).toBeDisabled(); // broken: not choosable
    expect(screen.getByRole("button", { name: /Sincronizza selezionati \(0\)/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("checkbox", { name: "Sincronizza Bot" }));
    fireEvent.click(screen.getByRole("button", { name: /Sincronizza selezionati \(1\)/ }));

    await waitFor(() => expect(synced).toHaveBeenCalled());
    expect(await screen.findByText(/🔄 aggiornato/)).toHaveTextContent("🔄 aggiornato · Chatbot Bot · global-chat-bot.yml");
  });

  it("selects every element that can be synced at once", async () => {
    mockApi({
      "GET /projects/acme": PROJECT,
      "GET /projects/acme/definitions": [
        { kind: "agent", file: "global-agent.yml", name: "hello", state: "new", message: "" },
        { kind: "automation", file: "a.yml", name: "Rotta", state: "error", message: "no" },
        { kind: "automation", file: "a.yml", name: "Buona", state: "new", message: "" },
      ],
    });
    inProject("settings", <SettingsTab />);

    fireEvent.click(await screen.findByRole("button", { name: /Definizioni da file/ }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Seleziona tutti" }));

    expect(screen.getByRole("button", { name: /Sincronizza selezionati \(2\)/ })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "Sincronizza Rotta" })).not.toBeChecked();
  });

  it("removes the project only after confirming, then goes back to the list", async () => {
    const removed = vi.fn(() => new Response(null, { status: 204 }));
    mockApi({ "GET /projects/acme": PROJECT, "DELETE /projects/acme": removed });
    inProject("settings", <SettingsTab />);

    fireEvent.click(await screen.findByRole("button", { name: /Rimuovi progetto/ })); // the section
    fireEvent.click(await screen.findByRole("button", { name: "Rimuovi progetto" })); // the button
    expect(removed).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Sì, rimuovi" }));

    expect(await screen.findByText("lista progetti")).toBeInTheDocument();
    expect(removed).toHaveBeenCalledTimes(1);
  });
});

describe("AgentsSection", () => {
  it("creates a project agent with the first active role and prompt version", async () => {
    const created = vi.fn(json);
    mockApi({
      "GET /agents": [],
      "GET /roles": [{ name: "old", project_name: null, description: "", active: false }, { name: "dev", project_name: null, description: "", active: true }],
      "GET /roles/dev/prompts": [{ id: 4, role_name: "dev", version: 2, text: "Sei uno sviluppatore.", active: true, created_at: "2026-10-25T10:00:00Z" }],
      "GET /tools": [{ name: "git_status", description: "", available: true, chatbot_only: false }, { name: "run_automation", description: "", available: true, chatbot_only: true }],
      "GET /models/choices": { choices: ["mock/echo"], usable: ["mock/echo"] },
      "POST /agents": created,
    });
    renderPage(<AgentsSection scope="acme" />);

    fireEvent.click(await screen.findByRole("button", { name: /Crea nuovo agente/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Nome/), { target: { value: "revisore" } });
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Salva" })).toBeEnabled());
    fireEvent.click(within(dialog).getByRole("button", { name: "Salva" }));

    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(await created.mock.results[0].value).toMatchObject({ name: "revisore", project_name: "acme", role_name: "dev", prompt_id: 4, tool_names: [] });
  });
});
