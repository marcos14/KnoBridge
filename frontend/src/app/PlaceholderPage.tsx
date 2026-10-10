import { useTranslation } from "react-i18next";

import type ptBR from "@/i18n/locales/pt-BR.json";

export type PlaceholderPageName = keyof (typeof ptBR)["pages"];

interface PlaceholderPageProps {
  page: PlaceholderPageName;
}

/**
 * Stand-in for a screen that does not exist yet: only a titled section, so the route tree and its
 * guards can be wired and tested. Each feature replaces its entry in `router.tsx`.
 */
export function PlaceholderPage({ page }: PlaceholderPageProps) {
  const { t } = useTranslation();

  return (
    <section>
      <h1>{t(`pages.${page}`)}</h1>
    </section>
  );
}
