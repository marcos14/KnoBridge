import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { type TicketsInboxCounts, useTicketsSummary } from "@/lib/api/tickets";
import { formatDateTime } from "@/lib/intl";

import { formatCount } from "../format";

/** Inbox states in the order a ticket goes through them. */
const COUNTS: readonly (keyof TicketsInboxCounts)[] = [
  "pending",
  "indexed",
  "filtered",
  "pending_delete",
  "deleted",
];

interface InboxSummaryProps {
  workspaceId: string;
  sourceId: string;
}

/**
 * Where the integration stands: the current send token (prefix and date, never the token) and
 * what arrived in the inbox, by state, with the entries that failed and the last arrival.
 */
export function InboxSummary({ workspaceId, sourceId }: InboxSummaryProps) {
  const { t, i18n } = useTranslation();
  const summary = useTicketsSummary(workspaceId, sourceId);
  const locale = i18n.language;

  if (summary.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("tickets.inbox.loading")}
      </p>
    );
  }
  if (summary.isError) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm">
          {t("tickets.inbox.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void summary.refetch();
          }}
        >
          {t("tickets.inbox.retry")}
        </Button>
      </div>
    );
  }

  const data = summary.data;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm">
        {data.token_prefix === null || data.token_created_at === null
          ? t("tickets.inbox.noToken")
          : t("tickets.inbox.token", {
              prefix: data.token_prefix,
              date: formatDateTime(new Date(data.token_created_at), locale),
            })}
      </p>
      <dl
        aria-label={t("tickets.inbox.countsLabel")}
        className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3"
      >
        {COUNTS.map((state) => (
          <div key={state} className="flex flex-col">
            <dt className="text-muted-foreground text-xs">{t(`tickets.inbox.states.${state}`)}</dt>
            <dd className="font-medium">{formatCount(data.counts[state], locale)}</dd>
          </div>
        ))}
      </dl>
      {data.failed > 0 && (
        <p className="text-destructive text-sm">
          {t("tickets.inbox.failed", {
            count: data.failed,
            formatted: formatCount(data.failed, locale),
          })}
        </p>
      )}
      <p className="text-muted-foreground text-sm">
        {data.last_received_at === null
          ? t("tickets.inbox.nothingReceived")
          : t("tickets.inbox.lastReceived", {
              date: formatDateTime(new Date(data.last_received_at), locale),
            })}
      </p>
    </div>
  );
}
