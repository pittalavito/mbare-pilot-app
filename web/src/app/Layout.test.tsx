import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Layout } from "./Layout";

afterEach(() => vi.unstubAllGlobals());

describe("Layout", () => {
  it("shows the sections and the API's state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ status: "ok" }), { status: 200 })));
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
  });
});
