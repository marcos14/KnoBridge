import { useTranslation } from "react-i18next";
import { Link } from "react-router";

/** 403: rendered in place by the guards, so the URL the user asked for stays in the address bar. */
export function ForbiddenPage() {
  const { t } = useTranslation();

  return (
    <section>
      <h1>{t("forbidden.title")}</h1>
      <p>{t("forbidden.description")}</p>
      <Link to="/">{t("forbidden.backHome")}</Link>
    </section>
  );
}
