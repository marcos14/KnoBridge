import { QueryClient } from "@tanstack/react-query";

export const DEFAULT_STALE_TIME_MS = 30_000;

/** Builds the app QueryClient; tests call it to get an isolated cache per render. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_STALE_TIME_MS,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
