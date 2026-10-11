import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { type Run, type RunError, useRun } from "@/lib/api/sources";
import { formatDateTime } from "@/lib/intl";

/** Errors per page (paged by the server). */
export const RUN_ERRORS_PAGE_SIZE = 20;

interface RunErrorsPanelProps {
  workspaceId: string;
  run: Run;
}

/** The failure of one run, if any, and the documents that failed in it, by step. */
export function RunErrorsPanel({ workspaceId, run }: RunErrorsPanelProps) {
  const { t, i18n } = useTranslation();
  const [offset, setOffset] = useState(0);
  const detail = useRun(workspaceId, run.id, { limit: RUN_ERRORS_PAGE_SIZE, offset });
  const when = formatDateTime(new Date(run.created_at), i18n.language);

  const columns: DataTableColumn<RunError>[] = [
    {
      key: "document",
      header: t("sources.errors.columns.document"),
      cell: (item) => <span className="font-mono text-xs break-all">{item.document_key}</span>,
    },
    {
      key: "stage",
      header: t("sources.errors.columns.stage"),
      cell: (item) => t(`sources.errors.stages.${item.stage}`),
    },
    {
      key: "code",
      header: t("sources.errors.columns.code"),
      cell: (item) => <code className="text-xs">{item.code}</code>,
    },
    { key: "message", header: t("sources.errors.columns.message"), cell: (item) => item.message },
  ];

  return (
    <section aria-labelledby="run-errors" className="flex flex-col gap-3">
      <h3 id="run-errors" className="font-semibold">
        {t("sources.errors.title", { when })}
      </h3>
      {detail.data === undefined ? (
        detail.isPending ? (
          <p role="status" className="text-sm">
            {t("sources.errors.loading")}
          </p>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm">
              {t("sources.errors.loadFailed")}
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
          {detail.data.error !== null && (
            <p className="bg-muted rounded-md px-3 py-2 text-sm">
              {t("sources.errors.failure", { error: detail.data.error })}
            </p>
          )}
          <DataTable
            label={t("sources.errors.tableLabel")}
            columns={columns}
            rows={detail.data.errors.items}
            rowKey={(item) => item.id}
            emptyMessage={t("sources.errors.empty")}
            busy={detail.isPlaceholderData}
            pagination={{
              offset,
              limit: RUN_ERRORS_PAGE_SIZE,
              total: detail.data.errors.total,
              onOffsetChange: setOffset,
            }}
          />
        </>
      )}
    </section>
  );
}
