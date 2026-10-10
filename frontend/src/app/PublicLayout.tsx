import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { ApiStatus } from "@/components/ApiStatus";

/** Frame of the pages used without a session (setup, login, password recovery, invitations). */
export function PublicLayout() {
  const { t } = useTranslation();

  return (
    <>
      <header className="flex items-center justify-between gap-4 border-b px-6 py-3">
        <p className="font-semibold">{t("app.title")}</p>
        <ApiStatus />
      </header>
      <main className="px-6 py-4">
        <Outlet />
      </main>
    </>
  );
}
