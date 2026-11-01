import { vi } from "vitest";

type Handler = (init?: RequestInit) => { status?: number; body?: unknown };

/**
 * Route-based fetch mock: keys are "<METHOD> <path>" without the /api/v1 prefix and
 * query string, e.g. "GET /me". Unmatched requests return 404 with an error envelope.
 */
export function mockFetch(routes: Record<string, Handler>) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const key = `${(init?.method ?? "GET").toUpperCase()} ${path}`;
    const handler = routes[key];
    const { status = 200, body = null } = handler
      ? handler(init)
      : { status: 404, body: { error: { code: "not_found", message: `No mock for ${key}`, retryable: false } } };
    return new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

export const unauthenticated = () => ({
  status: 401,
  body: { error: { code: "not_authenticated", message: "Please sign in to continue.", retryable: false } },
});
