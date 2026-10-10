import { render, type RenderResult } from "@testing-library/react";
import { createMemoryRouter, type RouteObject } from "react-router";

import { AppProviders } from "@/app/AppProviders";
import { createQueryClient } from "@/app/queryClient";
import { routes as appRoutes } from "@/app/router";
import { i18n } from "@/i18n";

interface RenderWithProvidersOptions {
  /** Initial URL of the in-memory router. Defaults to "/". */
  path?: string;
  /** Route tree to mount. Defaults to the app routes. */
  routes?: RouteObject[];
}

/** Renders a route tree with the same providers as the app, using an in-memory router. */
export function renderWithProviders({
  path = "/",
  routes = appRoutes,
}: RenderWithProvidersOptions = {}): RenderResult {
  const router = createMemoryRouter(routes, { initialEntries: [path] });

  return render(<AppProviders router={router} queryClient={createQueryClient()} i18n={i18n} />);
}
