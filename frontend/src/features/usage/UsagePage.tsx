import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { translateApiError } from "@/i18n/apiErrors";
import { useProducts } from "@/lib/api/products";
import { useExportUsage, useUsage, type UsageQuery } from "@/lib/api/usage";
import { searchDays, usageChatFilters, usagePeriod } from "@/lib/usagePeriod";

import { UsageDayChart } from "./UsageDayChart";
import { UsageFilterBar } from "./UsageFilterBar";
import { UsageTable } from "./UsageTable";
import { UsageTotals } from "./UsageTotals";
import { useUsageSearch } from "./useUsageSearch";

/** The report of the period and grouping in the URL, with its CSV export. */
function UsageReportView({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const clock = useClock();
  const { search, setSearch } = useUsageSearch();
  const now = clock();
  const chatFilters = usageChatFilters(search);
  const query: UsageQuery = { groupBy: search.group, ...usagePeriod(search, now), ...chatFilters };
  const chatOnly = chatFilters.productId !== undefined || chatFilters.level !== undefined;
  const report = useUsage(workspaceId, query);
  const exportCsv = useExportUsage(workspaceId);
  const products = useProducts(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <UsageFilterBar
          search={search}
          days={searchDays(search, now)}
          products={(products.data ?? []).map(({ id, name }) => ({ id, name }))}
          onChange={setSearch}
        />
        <Button
          type="button"
          variant="outline"
          disabled={exportCsv.isPending}
          onClick={() => {
            exportCsv.mutate(query);
          }}
        >
          <Download aria-hidden="true" />
          {exportCsv.isPending ? t("usage.exporting") : t("usage.export")}
        </Button>
      </div>
      {chatOnly && (
        <p className="text-muted-foreground text-sm">{t("usage.filters.filteredNote")}</p>
      )}
      {exportCsv.isError && (
        <p role="alert" className="text-destructive text-sm">
          {t("usage.exportFailed", { reason: translateApiError(exportCsv.error, t) })}
        </p>
      )}
      {report.isPending ? (
        <p role="status" className="text-sm">
          {t("usage.loading")}
        </p>
      ) : report.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("usage.loadFailed")} {translateApiError(report.error, t)}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void report.refetch();
            }}
          >
            {t("usage.retry")}
          </Button>
        </div>
      ) : (
        <>
          <UsageTotals report={report.data} busy={report.isPlaceholderData} />
          {report.data.group_by === "day" && <UsageDayChart rows={report.data.rows} />}
          <UsageTable
            key={report.data.group_by}
            group={report.data.group_by}
            chatOnly={chatOnly}
            rows={report.data.rows}
            totals={report.data.totals}
            busy={report.isPlaceholderData}
          />
        </>
      )}
    </div>
  );
}

/**
 * `/w/:workspaceId/usage` (owner or admin): tokens and estimated US$ of embeddings and chat in a
 * period, grouped, with totals, a chart per day and the CSV export.
 */
export function UsagePage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership and role.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("usage.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("usage.description")}</p>
      </div>
      {workspace !== undefined && <UsageReportView workspaceId={workspace.id} />}
    </div>
  );
}
