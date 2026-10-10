import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

/** Shown while a guard waits for the data it decides on. */
export function GuardLoading() {
  const { t } = useTranslation();

  return <p aria-busy="true">{t("authGuard.loading")}</p>;
}

interface GuardErrorProps {
  onRetry: () => void;
}

/** Shown when a guard could not load its data (API down, network failure). */
export function GuardError({ onRetry }: GuardErrorProps) {
  const { t } = useTranslation();

  return (
    <section role="alert" className="flex flex-col items-start gap-2">
      <p>{t("authGuard.loadFailed")}</p>
      <Button type="button" variant="outline" onClick={onRetry}>
        {t("authGuard.retry")}
      </Button>
    </section>
  );
}
