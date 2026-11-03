import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";

import { createQueryClient } from "./queryClient";

describe("createQueryClient", () => {
  it("retries network and retryable errors up to twice, never definitive ones", () => {
    const retry = createQueryClient().getDefaultOptions().queries?.retry as (count: number, error: unknown) => boolean;
    expect(retry(0, new TypeError("Failed to fetch"))).toBe(true);
    expect(retry(1, new ApiError(503, "unavailable", "Down", true))).toBe(true);
    expect(retry(2, new ApiError(503, "unavailable", "Down", true))).toBe(false);
    expect(retry(0, new ApiError(404, "unknown_symbol", "No such ticker", false))).toBe(false);
  });
});
