import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type HarnessJob,
  isHarnessJobActive,
  useCancelHarnessJob,
  useHarnessJobs,
} from "@/lib/api/harness";
import type { Source } from "@/lib/api/sources";
import { formatDateTime } from "@/lib/intl";

import { type Feedback, FeedbackMessage } from "../Feedback";
import { formatCount, formatUsd } from "../format";
import { HarnessJobStatusBadge } from "./HarnessJobStatusBadge";
import { jobDuration, jobTokens } from "./harnessFormat";
import { JobDetailPanel } from "./JobDetailPanel";
import { RunnerSetupHint } from "./RunnerSetupHint";

/** Jobs per page (paged by the server). */
export const JOBS_PAGE_SIZE = 20;

interface JobsTabProps {
  workspaceId: string;
  source: Source;
  canManage: boolean;
}

/**
 * The harness jobs of a runner source, newest first, refreshed while one has not finished:
 * module, status, trigger, executor, model, duration, cost, tokens and items accepted and
 * rejected. "Detalhes" picks the job shown below (the newest by default); owners, admins and
 * editors cancel the ones still active.
 */
export function JobsTab({ workspaceId, source, canManage }: JobsTabProps) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  const locale = i18n.language;
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const jobs = useHarnessJobs(workspaceId, source.id, { limit: JOBS_PAGE_SIZE, offset });
  const cancel = useCancelHarnessJob(workspaceId);
  const items = jobs.data?.items ?? [];
  const selected = items.find((job) => job.id === picked) ?? items[0];
  const when = (job: HarnessJob) => formatDateTime(new Date(job.created_at), locale);

  function onCancel(job: HarnessJob) {
    setFeedback(null);
    cancel.mutate(job.id, {
      onSuccess: () => {
        setFeedback({
          kind: "status",
          message: t("harness.jobs.cancelled", { title: job.module_title }),
        });
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  const columns: DataTableColumn<HarnessJob>[] = [
    {
      key: "module",
      header: t("harness.jobs.columns.module"),
      cell: (job) => <span className="font-medium">{job.module_title}</span>,
    },
    {
      key: "status",
      header: t("harness.jobs.columns.status"),
      cell: (job) => <HarnessJobStatusBadge status={job.status} />,
    },
    {
      key: "trigger",
      header: t("harness.jobs.columns.trigger"),
      cell: (job) => t(`harness.triggers.${job.trigger}`),
    },
    {
      key: "executor",
      header: t("harness.jobs.columns.executor"),
      cell: (job) => (
        <div className="flex flex-col">
          <span>{t(`runners.executors.${job.executor}`)}</span>
          <span className="text-muted-foreground text-xs">
            {job.model ?? t("harness.jobs.defaultModel")}
          </span>
        </div>
      ),
    },
    {
      key: "createdAt",
      header: t("harness.jobs.columns.createdAt"),
      cell: (job) => <time dateTime={job.created_at}>{when(job)}</time>,
    },
    {
      key: "duration",
      header: t("harness.jobs.columns.duration"),
      cell: (job) => jobDuration(job, clock()) ?? "—",
    },
    {
      key: "cost",
      header: t("harness.jobs.columns.cost"),
      className: "text-right",
      cell: (job) => formatUsd(job.cost_usd, locale),
    },
    {
      key: "tokens",
      header: t("harness.jobs.columns.tokens"),
      className: "text-right",
      cell: (job) => jobTokens(job, locale),
    },
    {
      key: "items",
      header: t("harness.jobs.columns.items"),
      className: "text-right",
      cell: (job) =>
        `${formatCount(job.items_accepted, locale)} / ${formatCount(job.items_rejected, locale)}`,
    },
    {
      key: "actions",
      header: t("harness.jobs.columns.actions"),
      cell: (job) => (
        <div className="flex flex-wrap gap-2">
          {job.id === selected?.id ? (
            <span className="text-sm font-medium">{t("harness.jobs.selected")}</span>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={t("harness.jobs.showLabel", { title: job.module_title, when: when(job) })}
              onClick={() => {
                setPicked(job.id);
              }}
            >
              {t("harness.jobs.show")}
            </Button>
          )}
          {canManage && isHarnessJobActive(job.status) && (
            <ConfirmDialog
              trigger={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={cancel.isPending}
                  aria-label={t("harness.jobs.cancelLabel", { title: job.module_title })}
                >
                  {t("harness.jobs.cancel")}
                </Button>
              }
              title={t("harness.jobs.cancelTitle", { title: job.module_title })}
              description={t("harness.jobs.cancelDescription")}
              confirmLabel={t("harness.jobs.cancelConfirm")}
              onConfirm={() => {
                onCancel(job);
              }}
            />
          )}
        </div>
      ),
    },
  ];

  if (jobs.data === undefined) {
    return jobs.isPending ? (
      <p role="status" className="text-sm">
        {t("harness.jobs.loading")}
      </p>
    ) : (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {t("harness.jobs.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void jobs.refetch();
          }}
        >
          {t("sources.retry")}
        </Button>
      </div>
    );
  }

  return (
    <section aria-labelledby="harness-jobs" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 id="harness-jobs" className="text-lg font-semibold">
          {t("harness.jobs.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("harness.jobs.description")}</p>
      </div>
      <FeedbackMessage feedback={feedback} />
      {jobs.data.total === 0 ? (
        <RunnerSetupHint
          workspaceId={workspaceId}
          source={source}
          canManage={canManage}
          message={t("harness.jobs.empty")}
        />
      ) : (
        <>
          <DataTable
            label={t("harness.jobs.tableLabel")}
            columns={columns}
            rows={items}
            rowKey={(job) => job.id}
            emptyMessage={t("harness.jobs.emptyPage")}
            busy={jobs.isPlaceholderData}
            pagination={{
              offset,
              limit: JOBS_PAGE_SIZE,
              total: jobs.data.total,
              onOffsetChange: setOffset,
            }}
          />
          {selected !== undefined && (
            <JobDetailPanel key={selected.id} workspaceId={workspaceId} job={selected} />
          )}
        </>
      )}
    </section>
  );
}
