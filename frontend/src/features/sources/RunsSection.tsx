import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import { type Run, useSourceRuns } from "@/lib/api/sources";
import { formatDateTime } from "@/lib/intl";

import { formatCount, formatUsd, runDuration } from "./format";
import { RunErrorsPanel } from "./RunErrorsPanel";
import { RunStatusBadge } from "./RunStatusBadge";

/** Runs per page (paged by the server). */
export const RUNS_PAGE_SIZE = 10;

interface RunsSectionProps {
  workspaceId: string;
  sourceId: string;
}

/**
 * The source's runs, newest first: status, trigger, document counts, chunks, tokens, cost and
 * duration, refreshed while one is active. "Ver erros" picks the run whose errors are listed
 * below (the newest by default).
 */
export function RunsSection({ workspaceId, sourceId }: RunsSectionProps) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const runs = useSourceRuns(workspaceId, sourceId, { limit: RUNS_PAGE_SIZE, offset });
  const locale = i18n.language;
  const items = runs.data?.items ?? [];
  const selected = items.find((run) => run.id === picked) ?? items[0];
  const when = (run: Run) => formatDateTime(new Date(run.created_at), locale);

  const columns: DataTableColumn<Run>[] = [
    {
      key: "status",
      header: t("sources.runs.columns.status"),
      cell: (run) => <RunStatusBadge status={run.status} />,
    },
    {
      key: "trigger",
      header: t("sources.runs.columns.trigger"),
      cell: (run) => t(`sources.triggers.${run.trigger}`),
    },
    {
      key: "createdAt",
      header: t("sources.runs.columns.createdAt"),
      cell: (run) => <time dateTime={run.created_at}>{when(run)}</time>,
    },
    {
      key: "documents",
      header: t("sources.runs.columns.documents"),
      cell: (run) =>
        [run.documents_new, run.documents_changed, run.documents_removed, run.documents_failed]
          .map((value) => formatCount(value, locale))
          .join(" / "),
    },
    {
      key: "chunks",
      header: t("sources.runs.columns.chunks"),
      className: "text-right",
      cell: (run) => formatCount(run.chunks_written, locale),
    },
    {
      key: "tokens",
      header: t("sources.runs.columns.tokens"),
      className: "text-right",
      cell: (run) => formatCount(run.embedding_tokens, locale),
    },
    {
      key: "cost",
      header: t("sources.runs.columns.cost"),
      className: "text-right",
      cell: (run) => formatUsd(run.cost_usd, locale),
    },
    {
      key: "duration",
      header: t("sources.runs.columns.duration"),
      cell: (run) => runDuration(run, clock()) ?? "—",
    },
    {
      key: "errors",
      header: t("sources.runs.columns.errors"),
      cell: (run) =>
        run.id === selected?.id ? (
          <span className="text-sm font-medium">{t("sources.runs.selected")}</span>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={t("sources.runs.showErrorsLabel", { when: when(run) })}
            onClick={() => {
              setPicked(run.id);
            }}
          >
            {t("sources.runs.showErrors")}
          </Button>
        ),
    },
  ];

  return (
    <section aria-labelledby="source-runs" className="flex flex-col gap-3">
      <h2 id="source-runs" className="text-lg font-semibold">
        {t("sources.runs.title")}
      </h2>
      {runs.data === undefined ? (
        runs.isPending ? (
          <p role="status" className="text-sm">
            {t("sources.runs.loading")}
          </p>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm">
              {t("sources.runs.loadFailed")}
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void runs.refetch();
              }}
            >
              {t("sources.retry")}
            </Button>
          </div>
        )
      ) : (
        <>
          <DataTable
            label={t("sources.runs.tableLabel")}
            columns={columns}
            rows={items}
            rowKey={(run) => run.id}
            emptyMessage={t("sources.runs.empty")}
            busy={runs.isPlaceholderData}
            pagination={{
              offset,
              limit: RUNS_PAGE_SIZE,
              total: runs.data.total,
              onOffsetChange: setOffset,
            }}
          />
          {selected !== undefined && (
            <RunErrorsPanel key={selected.id} workspaceId={workspaceId} run={selected} />
          )}
        </>
      )}
    </section>
  );
}
