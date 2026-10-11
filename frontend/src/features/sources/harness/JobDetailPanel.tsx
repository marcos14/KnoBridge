import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { type HarnessJob, type HarnessRejection, useHarnessJob } from "@/lib/api/harness";
import { formatDateTime } from "@/lib/intl";

import { formatCount } from "../format";
import { HarnessJobStatusBadge } from "./HarnessJobStatusBadge";
import {
  groupRejections,
  rejectionSourceLocation,
  rejectionSources,
  shortCommit,
} from "./harnessFormat";

/** Rejections per page: the server's largest page, so one page usually holds them all. */
export const REJECTIONS_PAGE_SIZE = 300;

/** Codes of the runner's verification (`docs/specs/harness.md`, "Verificação mecânica"). */
const SOURCE_CODES = [
  "file_not_found",
  "outside_checkout",
  "bad_range",
  "range_too_long",
  "symbol_mismatch",
  "no_valid_source",
] as const;

interface JobDetailPanelProps {
  workspaceId: string;
  job: HarnessJob;
}

/** One job: where and how it ran, its failure, and the items the verification rejected, by reason. */
export function JobDetailPanel({ workspaceId, job }: JobDetailPanelProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const [offset, setOffset] = useState(0);
  const detail = useHarnessJob(workspaceId, job.id, { limit: REJECTIONS_PAGE_SIZE, offset });
  const instant = (value: string | null) =>
    value === null ? "—" : formatDateTime(new Date(value), locale);

  function sourceCode(code: string | null): string | null {
    const known = SOURCE_CODES.find((item) => item === code);
    return known === undefined ? code : t(`harness.rejectionCodes.${known}`);
  }

  const columns: DataTableColumn<HarnessRejection>[] = [
    {
      key: "reason",
      header: t("harness.rejections.columns.reason"),
      cell: (rejection) => rejection.reason,
    },
    {
      key: "block",
      header: t("harness.rejections.columns.block"),
      cell: (rejection) => t(`harness.blocks.${rejection.block}`),
    },
    {
      key: "item",
      header: t("harness.rejections.columns.item"),
      cell: (rejection) => rejection.label,
    },
    {
      key: "sources",
      header: t("harness.rejections.columns.sources"),
      cell: (rejection) => {
        const sources = rejectionSources(rejection);
        return sources.length === 0 ? (
          t("harness.rejections.noSources")
        ) : (
          <ul className="flex flex-col gap-1">
            {sources.map((source, index) => (
              <li key={index} className="text-xs">
                <code className="break-all">
                  {rejectionSourceLocation(source) ?? t("harness.rejections.unsafePath")}
                </code>
                {source.code !== null && (
                  <span className="text-muted-foreground"> — {sourceCode(source.code)}</span>
                )}
              </li>
            ))}
          </ul>
        );
      },
    },
  ];

  return (
    <section aria-labelledby="harness-job-detail" className="flex flex-col gap-3">
      <h3 id="harness-job-detail" className="font-semibold">
        {t("harness.jobDetail.title", { title: job.module_title, when: instant(job.created_at) })}
      </h3>
      {detail.data === undefined ? (
        detail.isPending ? (
          <p role="status" className="text-sm">
            {t("harness.jobDetail.loading")}
          </p>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm">
              {t("harness.jobDetail.loadFailed")}
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void detail.refetch();
              }}
            >
              {t("sources.retry")}
            </Button>
          </div>
        )
      ) : (
        <>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t("harness.jobDetail.status")}</dt>
            <dd>
              <HarnessJobStatusBadge status={detail.data.status} />
            </dd>
            <dt className="text-muted-foreground">{t("harness.jobDetail.executor")}</dt>
            <dd>
              {t(`runners.executors.${detail.data.executor}`)} ·{" "}
              {detail.data.model ?? t("harness.jobs.defaultModel")}
            </dd>
            <dt className="text-muted-foreground">{t("harness.jobDetail.commit")}</dt>
            <dd>
              {detail.data.commit_sha === null ? (
                "—"
              ) : (
                <code title={detail.data.commit_sha}>{shortCommit(detail.data.commit_sha)}</code>
              )}
            </dd>
            <dt className="text-muted-foreground">{t("harness.jobDetail.attempts")}</dt>
            <dd>{formatCount(detail.data.attempts, locale)}</dd>
            <dt className="text-muted-foreground">{t("harness.jobDetail.startedAt")}</dt>
            <dd>{instant(detail.data.started_at)}</dd>
            <dt className="text-muted-foreground">{t("harness.jobDetail.finishedAt")}</dt>
            <dd>{instant(detail.data.finished_at)}</dd>
            {detail.data.not_before !== null && (
              <>
                <dt className="text-muted-foreground">{t("harness.jobDetail.notBefore")}</dt>
                <dd>{instant(detail.data.not_before)}</dd>
              </>
            )}
          </dl>
          {detail.data.error !== null && (
            <p className="bg-muted rounded-md px-3 py-2 text-sm">
              {t("harness.jobDetail.error", { error: detail.data.error })}
            </p>
          )}
          <h4 className="text-sm font-semibold">
            {t("harness.rejections.title", { count: detail.data.rejections.total })}
          </h4>
          {detail.data.rejections.total > 0 && (
            <ul aria-label={t("harness.rejections.byReason")} className="flex flex-col gap-1">
              {groupRejections(detail.data.rejections.items).map((group) => (
                <li key={group.code} className="text-sm">
                  {t("harness.rejections.group", { reason: group.reason, count: group.count })}
                </li>
              ))}
            </ul>
          )}
          <DataTable
            label={t("harness.rejections.tableLabel")}
            columns={columns}
            rows={detail.data.rejections.items}
            rowKey={(rejection) => rejection.id}
            emptyMessage={t("harness.rejections.empty")}
            busy={detail.isPlaceholderData}
            pagination={{
              offset,
              limit: REJECTIONS_PAGE_SIZE,
              total: detail.data.rejections.total,
              onOffsetChange: setOffset,
            }}
          />
        </>
      )}
    </section>
  );
}
