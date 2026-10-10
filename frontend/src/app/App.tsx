import { useState } from "react";

import { i18n } from "@/i18n";

import { AppProviders } from "./AppProviders";
import { createQueryClient } from "./queryClient";
import { createAppRouter } from "./router";

export function App() {
  // Lazy state keeps one router and one cache for the lifetime of the app, across re-renders.
  const [router] = useState(createAppRouter);
  const [queryClient] = useState(createQueryClient);

  return <AppProviders router={router} queryClient={queryClient} i18n={i18n} />;
}
