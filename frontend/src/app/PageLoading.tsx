import { useTranslation } from "react-i18next";

/** Shown in place of a page while its code arrives (`lazyPage`); the shell around it stays. */
export function PageLoading() {
  const { t } = useTranslation();

  return (
    <p role="status" className="text-muted-foreground text-sm">
      {t("app.loadingPage")}
    </p>
  );
}
