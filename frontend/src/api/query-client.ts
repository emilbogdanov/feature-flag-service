import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./client";

const MAX_RETRIES = 2;
// Long enough that going back to a page just seen, or a list the sign-in check already loaded,
// doesn't ask again; short enough that changes made elsewhere show up on the next visit.
const STALE_AFTER_MS = 15_000;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: STALE_AFTER_MS,
        // An answer from the API that the request was wrong won't change by asking again; a
        // dropped connection or a restarting instance might.
        retry: (failures, error) => isRetryable(error) && failures < MAX_RETRIES,
      },
    },
  });
}

function isRetryable(error: unknown): boolean {
  return !(error instanceof ApiError && error.status < 500);
}
