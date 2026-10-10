import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { ApiStatus } from "@/components/ApiStatus";
import { SessionExpiryHandler } from "@/features/auth/SessionExpiryHandler";

export function Layout() {
  const { t } = useTranslation();

  return (
    <>
      <header className="flex items-center justify-between gap-4 border-b px-6 py-3">
        <p className="font-semibold">{t("app.title")}</p>
        <nav aria-label={t("nav.label")} />
        <ApiStatus />
      </header>
      <main className="px-6 py-4">
        <SessionExpiryHandler />
        <Outlet />
      </main>
    </>
  );
}
