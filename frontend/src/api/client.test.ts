import { describe, expect, it, vi } from "vitest";

import { mockFetch } from "@/test/mockFetch";

import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  it("returns parsed JSON and sends JSON bodies", async () => {
    const spy = mockFetch({ "PUT /me/profile": (init) => ({ body: JSON.parse(String(init?.body)) }) });
    const result = await apiFetch<{ a: number }>("/me/profile", { method: "PUT", body: JSON.stringify({ a: 1 }) });
    expect(result).toEqual({ a: 1 });
    const headers = spy.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("returns undefined for 204", async () => {
    mockFetch({ "POST /auth/logout": () => ({ status: 204 }) });
    await expect(apiFetch("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("maps the error envelope onto ApiError", async () => {
    mockFetch({
      "GET /me": () => ({ status: 401, body: { error: { code: "not_authenticated", message: "Sign in", retryable: false } } }),
    });
    const error = await apiFetch("/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, code: "not_authenticated", message: "Sign in", retryable: false });
    expect((error as ApiError).isUnauthenticated).toBe(true);
  });

  it("handles non-envelope errors and network failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 500 })));
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 500, code: "http_error" });

    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    await expect(apiFetch("/x")).rejects.toMatchObject({ code: "network_error", retryable: true });
  });
});
