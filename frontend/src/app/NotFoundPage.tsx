import { useTranslation } from "react-i18next";
import { Link } from "react-router";

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <section>
      <h1>{t("notFound.title")}</h1>
      <p>{t("notFound.description")}</p>
      <Link to="/">{t("notFound.backHome")}</Link>
    </section>
  );
}
