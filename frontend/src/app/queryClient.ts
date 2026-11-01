import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Retry only what the backend marks retryable (or network failures).
        retry: (count, error) => count < 2 && (!(error instanceof ApiError) || error.retryable),
        refetchOnWindowFocus: false,
      },
    },
  });
}
