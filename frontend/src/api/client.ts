import type { ErrorEnvelope } from "./types";

export const API_PREFIX = "/api/v1";

/** An error from the API, carrying the backend's {code, message, retryable} envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string, retryable = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

function isEnvelope(body: unknown): body is ErrorEnvelope {
  return typeof body === "object" && body !== null && "error" in body;
}

export async function toApiError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  if (isEnvelope(body)) {
    const { code, message, retryable } = body.error;
    return new ApiError(response.status, code, message, retryable ?? false);
  }
  return new ApiError(response.status, "http_error", `Request failed (${response.status}).`);
}

/**
 * Fetch JSON from the backend. Cookies ride along automatically (same origin), so no
 * token is ever handled in JavaScript.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      credentials: "same-origin",
      ...init,
      headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
    });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection.", true);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
