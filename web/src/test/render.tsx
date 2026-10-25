import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

/** Answers of the fake API: "METHOD /path" -> JSON body, or a function of the
 * request (query string, body) returning one. Anything else answers 404. */
export type Answers = Record<string, unknown | ((request: Request) => unknown | Promise<unknown>)>;

/** Replace fetch with the fake API; returns the mock to inspect the calls. */
export function mockApi(answers: Answers) {
  const fetchMock = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    const answer = answers[`${request.method} ${decodeURIComponent(url.pathname).replace(/^\/api/, "")}`];
    if (answer === undefined) {
      return new Response(JSON.stringify({ detail: `non previsto: ${request.method} ${url.pathname}` }), { status: 404 });
    }
    const body = typeof answer === "function" ? await answer(request) : answer;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** A page with the app's providers, at ``route`` matched by ``path``. */
export function renderPage(ui: ReactElement, { route = "/", path = "/*" }: { route?: string; path?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <ModalsProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[route]}>
            <Routes>
              <Route path={path} element={ui} />
              <Route path="*" element={<div>altra pagina</div>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </ModalsProvider>
    </MantineProvider>,
  );
}
