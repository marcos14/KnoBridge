import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import type { i18n as I18n } from "i18next";
import { I18nextProvider } from "react-i18next";
import { RouterProvider, type createBrowserRouter } from "react-router";

export type AppRouter = ReturnType<typeof createBrowserRouter>;

interface AppProvidersProps {
  router: AppRouter;
  queryClient: QueryClient;
  i18n: I18n;
}

/** Provider stack shared by the real app and the test helper, so both render the same tree. */
export function AppProviders({ router, queryClient, i18n }: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={i18n}>
        <RouterProvider router={router} />
      </I18nextProvider>
    </QueryClientProvider>
  );
}
