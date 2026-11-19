import { fireEvent, screen } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { PROJECT_API, projectRoutes } from "../../test/zones";

afterEach(() => vi.unstubAllGlobals());

describe("«🗄 Archivio» (plan 33)", () => {
  it("lists the archived activities and shows their summary", async () => {
    mockApi({
      ...PROJECT_API,
      "GET /projects/acme/notes": [
        { name: "archivio-login.md", kind: "note", size: 1, modified_at: "2026-11-19T10:00:00Z", note_type: "generic" },
        { name: "appunti.md", kind: "note", size: 1, modified_at: "2026-11-19T10:00:00Z", note_type: "generic" },
      ],
      "GET /projects/acme/notes/archivio-login.md": { name: "archivio-login.md", content: "# Archivio: Login\n\n## Task\n- ✓ Analizza (analysis)" },
    });
    renderPage(<Routes>{projectRoutes()}</Routes>, { route: "/projects/acme/work" });

    fireEvent.click(await screen.findByRole("tab", { name: /Archivio/ }));
    expect(await screen.findByText("Archivio: Login")).toBeInTheDocument();
    expect(screen.getByText("login")).toBeInTheDocument();
    expect(screen.queryByText("appunti")).not.toBeInTheDocument();
  });

  it("says how to archive when there is nothing", async () => {
    mockApi({ ...PROJECT_API });
    renderPage(<Routes>{projectRoutes()}</Routes>, { route: "/projects/acme/work?view=archive" });
    expect(await screen.findByText(/Nessuna attività archiviata/)).toBeInTheDocument();
  });
});
