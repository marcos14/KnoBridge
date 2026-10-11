import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type Source, useSources } from "@/lib/api/sources";

interface CollectionSourcesProps {
  workspaceId: string;
  collectionId: string;
}

/** The sources that feed the collection, with their documents and last sync (read only here). */
export function CollectionSources({ workspaceId, collectionId }: CollectionSourcesProps) {
  const { t } = useTranslation();
  const sources = useSources(workspaceId, collectionId);

  const columns: DataTableColumn<Source>[] = [
    { key: "name", header: t("collections.detail.columns.name"), cell: (item) => item.name },
    {
      key: "kind",
      header: t("collections.detail.columns.kind"),
      cell: (item) => t(`collections.detail.kinds.${item.kind}`),
    },
    {
      key: "documents",
      header: t("collections.detail.columns.documents"),
      className: "text-right",
      cell: (item) => item.document_count,
    },
    {
      key: "lastRun",
      header: t("collections.detail.columns.lastRun"),
      cell: (item) => (
        <Badge variant={item.last_run?.status === "failed" ? "destructive" : "secondary"}>
          {t(`collections.detail.runStatus.${item.last_run?.status ?? "never"}`)}
        </Badge>
      ),
    },
  ];

  return (
    <section aria-labelledby="collection-sources" className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 id="collection-sources" className="text-lg font-semibold">
          {t("collections.detail.sourcesTitle")}
        </h2>
        <p className="text-muted-foreground text-sm">
          {t("collections.detail.sourcesHint")}{" "}
          <Link to={`/w/${workspaceId}/sources`} className="underline underline-offset-4">
            {t("collections.detail.goToSources")}
          </Link>
        </p>
      </div>
      {sources.isPending ? (
        <p role="status" className="text-sm">
          {t("collections.detail.sourcesLoading")}
        </p>
      ) : sources.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("collections.detail.sourcesLoadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void sources.refetch();
            }}
          >
            {t("collections.retry")}
          </Button>
        </div>
      ) : (
        <DataTable
          label={t("collections.detail.sourcesTableLabel")}
          columns={columns}
          rows={sources.data}
          rowKey={(item) => item.id}
          emptyMessage={t("collections.detail.sourcesEmpty")}
        />
      )}
    </section>
  );
}
