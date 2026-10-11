import { Inbox } from "lucide-react";
import { useTranslation } from "react-i18next";

export type SkeletonArea = "pipelines" | "channels";

interface AreaSkeletonPageProps {
  area: SkeletonArea;
}

/**
 * Skeleton of an area whose feature arrives in a later plan: title and an empty state that says
 * what will live there. The feature replaces it in `router.tsx`.
 */
export function AreaSkeletonPage({ area }: AreaSkeletonPageProps) {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t(`areas.${area}.title`)}</h1>
      <div className="text-muted-foreground flex max-w-prose flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center">
        <Inbox className="size-8" aria-hidden="true" />
        <h2 className="text-foreground font-medium">{t("areas.emptyTitle")}</h2>
        <p>{t(`areas.${area}.description`)}</p>
      </div>
    </section>
  );
}
