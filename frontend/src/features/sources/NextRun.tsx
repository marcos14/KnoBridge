import { useTranslation } from "react-i18next";

import type { Source } from "@/lib/api/sources";

import { cronText } from "./format";
import { RelativeTime } from "./RelativeTime";

/** When the schedule runs next (and the schedule in words), or why it does not. */
export function NextRun({ source }: { source: Source }) {
  const { t, i18n } = useTranslation();
  const { next_run_at: next, schedule_cron: cron } = source;

  if (next !== null && cron !== null) {
    return (
      <div className="flex flex-col">
        <RelativeTime value={next} />
        <span className="text-muted-foreground text-xs">{cronText(cron, t, i18n.language)}</span>
      </div>
    );
  }
  return (
    <span className="text-muted-foreground text-sm">
      {cron !== null && !source.schedule_enabled
        ? t("sources.schedulePaused")
        : t("sources.noSchedule")}
    </span>
  );
}
