import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { ConversationStats } from "@/lib/api/workspaceConversations";
import { formatDate } from "@/lib/intl";

interface ConversationStatsCardsProps {
  stats: UseQueryResult<ConversationStats>;
}

/** Cards in reading order, with the total each one shows. */
const TOTALS = [
  { key: "conversations", label: "conversations.stats.conversations" },
  { key: "messages", label: "conversations.stats.messages" },
  { key: "thumbs_up", label: "conversations.stats.thumbsUp" },
  { key: "thumbs_down", label: "conversations.stats.thumbsDown" },
  { key: "no_source_answers", label: "conversations.stats.noSource" },
  { key: "failed_answers", label: "conversations.stats.failed" },
  { key: "interrupted_answers", label: "conversations.stats.interrupted" },
] as const satisfies readonly { key: keyof ConversationStats; label: string }[];

/**
 * Totals of the period the filters choose (the API's last 30 days without one). The period comes
 * back half-open, `[start, end)`: the last day shown is the one just before `end`.
 */
export function ConversationStatsCards({ stats }: ConversationStatsCardsProps) {
  const { t, i18n } = useTranslation();

  if (stats.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("conversations.stats.loading")}
      </p>
    );
  }
  if (stats.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("conversations.stats.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void stats.refetch();
          }}
        >
          {t("conversations.retry")}
        </Button>
      </div>
    );
  }

  const { data } = stats;
  const start = formatDate(new Date(data.period_start), i18n.language);
  const end = formatDate(new Date(Date.parse(data.period_end) - 1), i18n.language);

  return (
    <section
      aria-label={t("conversations.stats.label")}
      aria-busy={stats.isPlaceholderData}
      className="flex flex-col gap-2"
    >
      <p className="text-muted-foreground text-sm">
        {t("conversations.stats.period", { start, end })}
      </p>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {TOTALS.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-1 rounded-md border p-3">
            <dt className="text-muted-foreground text-xs">{t(label)}</dt>
            <dd className="text-2xl font-semibold tabular-nums">
              {data[key].toLocaleString(i18n.language)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
