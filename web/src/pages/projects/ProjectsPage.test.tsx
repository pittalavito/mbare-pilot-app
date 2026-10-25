import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { ProjectsPage } from "./ProjectsPage";

afterEach(() => vi.unstubAllGlobals());

const PROJECT = {
  name: "Gestionali Navi",
  description: "Gestionale navi",
  source: "folder",
  root_path: "C:\\code\\navi",
  embedding_model: "openai/text-embedding-3-small",
  created_at: "2026-10-25T10:00:00Z",
  folder_exists: false,
};

const FOLDERS = {
  "GET /folders/roots": { roots: ["C:\\code"] },
  "GET /folders": (request: Request) => {
    const path = new URL(request.url).searchParams.get("path") || "C:\\code";
    const children = path === "C:\\code" ? [{ name: "nuovo", path: "C:\\code\\nuovo" }] : [];
    return { path, parent: path === "C:\\code" ? null : "C:\\code", subfolders: children };
  },
};

describe("ProjectsPage", () => {
  it("lists the projects, warning when a folder is gone", async () => {
    mockApi({ "GET /projects": [PROJECT] });
    renderPage(<ProjectsPage />, { route: "/projects", path: "/projects" });

    expect(await screen.findByText("Gestionali Navi")).toBeInTheDocument();
    expect(screen.getByText("C:\\code\\navi")).toBeInTheDocument();
    expect(screen.getByText("La cartella non esiste più sul disco.")).toBeInTheDocument();
  });

  it("explains what to do without projects", async () => {
    mockApi({ "GET /projects": [] });
    renderPage(<ProjectsPage />, { route: "/projects", path: "/projects" });

    expect(await screen.findByText(/Nessun progetto/)).toBeInTheDocument();
  });

  it("opens a folder picked in the browser and goes to the new project", async () => {
    const opened: unknown[] = [];
    mockApi({
      "GET /projects": [],
      ...FOLDERS,
      "POST /projects/open-folder": async (request: Request) => {
        opened.push(await request.json());
        return { ...PROJECT, name: "nuovo", folder_exists: true };
      },
    });
    renderPage(<ProjectsPage />, { route: "/projects", path: "/projects" });

    fireEvent.click(await screen.findByRole("button", { name: "Apri cartella" }));
    fireEvent.click(await screen.findByText("nuovo"));
    await screen.findByText("C:\\code\\nuovo", { selector: "code" });
    fireEvent.change(screen.getByLabelText("Descrizione"), { target: { value: "Il progetto nuovo" } });
    fireEvent.click(screen.getByRole("button", { name: "Apri come progetto" }));

    expect(await screen.findByText("altra pagina")).toBeInTheDocument(); // navigated to /projects/nuovo
    expect(opened).toEqual([{ folder: "C:\\code\\nuovo", name: "", description: "Il progetto nuovo" }]);
  });

  it("shows the API's error inside the dialog", async () => {
    mockApi({
      "GET /projects": [],
      ...FOLDERS,
      "POST /projects/open-folder": () =>
        new Response(JSON.stringify({ detail: "Esiste già un progetto in questa cartella." }), { status: 409 }),
    });
    renderPage(<ProjectsPage />, { route: "/projects", path: "/projects" });

    fireEvent.click(await screen.findByRole("button", { name: "Apri cartella" }));
    await screen.findByText("nuovo");
    await waitFor(() => expect(screen.getByRole("button", { name: "Apri come progetto" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Apri come progetto" }));

    expect(await screen.findByText("Esiste già un progetto in questa cartella.")).toBeInTheDocument();
  });
});
