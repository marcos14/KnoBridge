import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

import { ApiStatus } from "@/components/ApiStatus";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

import { AppSidebar } from "./AppSidebar";
import { SuperadminAccessBanner } from "./SuperadminAccessBanner";
import { UserMenu } from "./UserMenu";

const MAIN_ID = "main-content";

/**
 * Frame of every authenticated page: skip link, side menu, top bar (menu toggle, API status, user
 * menu) and the `main` landmark where the route renders, 403 and 404 included.
 */
export function AppShell() {
  const { t } = useTranslation();

  return (
    <SidebarProvider>
      <a
        href={`#${MAIN_ID}`}
        className="bg-background sr-only z-50 rounded-md px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        {t("shell.skipToContent")}
      </a>
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <SuperadminAccessBanner />
        <header className="flex h-14 items-center gap-2 border-b px-4">
          <SidebarTrigger aria-label={t("shell.toggleSidebar")} />
          <p className="font-semibold">{t("app.title")}</p>
          <div className="ml-auto flex items-center gap-3">
            <ApiStatus />
            <UserMenu />
          </div>
        </header>
        <main id={MAIN_ID} tabIndex={-1} className="flex-1 px-6 py-4 outline-none">
          <Outlet />
        </main>
      </div>
    </SidebarProvider>
  );
}
