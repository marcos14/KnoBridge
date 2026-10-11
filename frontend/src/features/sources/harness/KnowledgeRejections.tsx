import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useHarnessJob } from "@/lib/api/harness";
import { formatDateTime } from "@/lib/intl";

import { REJECTIONS_PAGE_SIZE } from "./JobDetailPanel";
import { groupRejections, rejectionSourceLocation, rejectionSources } from "./harnessFormat";

interface KnowledgeRejectionsProps {
  workspaceId: string;
  /** The module's latest job with a result (`latestModuleJobId`), or `null` without one. */
  jobId: string | null;
}

/**
 * What the verification refused in the module's latest result, with the runner's reason and the
 * cited sources: read from the job detail (the API keeps rejections per job, not per item).
 */
export function KnowledgeRejections({ workspaceId, jobId }: KnowledgeRejectionsProps) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="knowledge-rejections" className="flex flex-col gap-2">
      <h3 id="knowledge-rejections" className="font-semibold">
        {t("harness.knowledge.rejections.title")}
      </h3>
      <p className="text-muted-foreground text-sm">
        {t("harness.knowledge.rejections.description")}
      </p>
      {jobId === null ? (
        <p className="text-sm">{t("harness.knowledge.rejections.noJob")}</p>
      ) : (
        <JobRejections workspaceId={workspaceId} jobId={jobId} />
      )}
    </section>
  );
}

function JobRejections({ workspaceId, jobId }: { workspaceId: string; jobId: string }) {
  const { t, i18n } = useTranslation();
  const detail = useHarnessJob(workspaceId, jobId, { limit: REJECTIONS_PAGE_SIZE, offset: 0 });

  if (detail.data === undefined) {
    return detail.isPending ? (
      <p role="status" className="text-sm">
        {t("harness.knowledge.rejections.loading")}
      </p>
    ) : (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-sm">
          {t("harness.knowledge.rejections.loadFailed")}
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
    );
  }

  const { rejections } = detail.data;
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="text-muted-foreground">
        {t("harness.knowledge.rejections.job", {
          when: formatDateTime(new Date(detail.data.created_at), i18n.language),
        })}{" "}
        · {t("harness.rejections.title", { count: rejections.total })}
      </p>
      {rejections.total > 0 && (
        <>
          <ul aria-label={t("harness.rejections.byReason")} className="flex flex-col gap-1">
            {groupRejections(rejections.items).map((group) => (
              <li key={group.code}>
                {t("harness.rejections.group", { reason: group.reason, count: group.count })}
              </li>
            ))}
          </ul>
          <ul
            aria-label={t("harness.knowledge.rejections.listLabel")}
            className="flex flex-col gap-2"
          >
            {rejections.items.map((rejection) => (
              <li key={rejection.id} className="rounded-md border px-3 py-2">
                <p className="font-medium">
                  {t("harness.knowledge.rejections.item", {
                    label: rejection.label,
                    block: t(`harness.blocks.${rejection.block}`),
                  })}
                </p>
                <p className="text-muted-foreground">{rejection.reason}</p>
                {rejectionSources(rejection).map((source, index) => (
                  <code key={index} className="block text-xs break-all">
                    {rejectionSourceLocation(source) ?? t("harness.rejections.unsafePath")}
                  </code>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
