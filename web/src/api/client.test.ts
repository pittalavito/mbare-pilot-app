import { describe, expect, it } from "vitest";

import { ApiError, detail, unwrap } from "./client";

const response = (status: number) => new Response(null, { status, statusText: status === 404 ? "Not Found" : "" });

describe("unwrap", () => {
  it("returns the data of a successful call", async () => {
    await expect(unwrap(Promise.resolve({ data: [1, 2], response: response(200) }))).resolves.toEqual([1, 2]);
  });

  it("throws the backend's message", async () => {
    const call = Promise.resolve({ error: { detail: "Progetto non trovato: x" }, response: response(404) });
    await expect(unwrap(call)).rejects.toMatchObject({ status: 404, message: "Progetto non trovato: x" });
  });

  it("explains an unreachable API", async () => {
    const error = await unwrap(Promise.reject(new TypeError("fetch failed"))).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, message: expect.stringContaining("non raggiungibile") });
  });
});

describe("detail", () => {
  it("joins FastAPI's validation errors", () => {
    expect(detail({ detail: [{ msg: "campo obbligatorio" }, { msg: "troppo lungo" }] })).toBe("campo obbligatorio; troppo lungo");
  });
});
