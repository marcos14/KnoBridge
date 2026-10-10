import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { i18n as I18n } from "i18next";
import { I18nextProvider } from "react-i18next";
import { RouterProvider, type createBrowserRouter } from "react-router";

import { type Clock, ClockContext, systemClock } from "@/hooks/use-clock";

export type AppRouter = ReturnType<typeof createBrowserRouter>;

interface AppProvidersProps {
  router: AppRouter;
  queryClient: QueryClient;
  i18n: I18n;
  /** Source of "now" for relative dates; tests pin it, the app uses the system clock. */
  clock?: Clock;
}

/** Provider stack shared by the real app and the test helper, so both render the same tree. */
export function AppProviders({
  router,
  queryClient,
  i18n,
  clock = systemClock,
}: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={i18n}>
        <ClockContext value={clock}>
          <RouterProvider router={router} />
        </ClockContext>
      </I18nextProvider>
    </QueryClientProvider>
  );
}
