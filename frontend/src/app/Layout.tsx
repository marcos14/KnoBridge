import { useTranslation } from "react-i18next";
import { Outlet } from "react-router";

export function Layout() {
  const { t } = useTranslation();

  return (
    <>
      <header>
        <p>{t("app.title")}</p>
        <nav aria-label={t("nav.label")} />
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}
