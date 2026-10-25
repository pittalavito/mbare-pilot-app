import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Layout } from "./Layout";

afterEach(() => vi.unstubAllGlobals());

describe("Layout", () => {
  it("shows the sections and the state of the API and the worker", async () => {
    const answers: Record<string, unknown> = {
      "/api/health": { status: "ok" },
      "/api/admin/worker": { status: "stopped", pid: null, workers: [] },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) => {
        const body = answers[new URL(request.url).pathname];
        return new Response(JSON.stringify(body ?? {}), { status: body ? 200 : 404 });
      }),
    );
    render(
      <MantineProvider>
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter initialEntries={["/projects"]}>
            <Routes>
              <Route path="/*" element={<Layout />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );

    for (const section of ["Progetti", "Libreria", "Admin"]) {
      expect(screen.getByText(section)).toBeInTheDocument();
    }
    expect(await screen.findByText("API attiva")).toBeInTheDocument();
    expect(await screen.findByText("Worker fermo")).toBeInTheDocument();
  });
});
