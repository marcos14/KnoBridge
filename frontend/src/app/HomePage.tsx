import { useTranslation } from "react-i18next";

export function HomePage() {
  const { t } = useTranslation();

  return (
    <section>
      <h1>{t("home.title")}</h1>
      <p>{t("home.description")}</p>
    </section>
  );
}
