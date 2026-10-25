import createClient from "openapi-fetch";

import type { paths } from "./schema";

/**
 * The API, typed from its OpenAPI schema (`npm run gen:api`). In development
 * Vite proxies `/api` to the API (API_URL of the .env). The base URL is
 * absolute and `fetch` is looked up at every call (not captured once), so the
 * same client works in the browser and in the tests.
 */
export const api = createClient<paths>({
  baseUrl: `${window.location.origin}/api`,
  fetch: (request) => globalThis.fetch(request),
});

/** An API error carrying the backend's message (FastAPI `detail`), ready to show. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** The data of a call, or an ApiError with the backend's message (status 0 = API unreachable). */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, "API non raggiungibile: avviala e riprova.");
  }
  const { data, error, response } = result;
  if (error !== undefined || !response.ok) {
    throw new ApiError(response.status, detail(error) ?? (response.statusText || `Errore ${response.status}`));
  }
  return data as T;
}

/** FastAPI's `detail`: a message, or the list of validation errors (joined). */
export function detail(error: unknown): string | undefined {
  if (!error || typeof error !== "object" || !("detail" in error)) return undefined;
  const value = (error as { detail: unknown }).detail;
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : String(item)))
      .join("; ");
  }
  return undefined;
}
