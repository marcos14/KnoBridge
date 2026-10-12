import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FilterSelect } from "@/components/FilterSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { type DocumentKind, type SourceDocument, useSourceDocuments } from "@/lib/api/sources";
import { formatDateTime } from "@/lib/intl";

import { formatCount } from "./format";

/** Documents per page (paged by the server). */
export const DOCUMENTS_PAGE_SIZE = 20;

const ALL = "all";

interface DocumentsSectionProps {
  workspaceId: string;
  sourceId: string;
}

/** The documents indexed from the source, searchable by path and filtered by kind. */
export function DocumentsSection({ workspaceId, sourceId }: DocumentsSectionProps) {
  const { t, i18n } = useTranslation();
  const pathId = useId();
  const kindId = useId();
  const [typed, setTyped] = useState("");
  const [path, setPath] = useState<string | undefined>(undefined);
  const [kind, setKind] = useState<DocumentKind | undefined>(undefined);
  const [offset, setOffset] = useState(0);
  const documents = useSourceDocuments(workspaceId, sourceId, {
    path,
    kind,
    limit: DOCUMENTS_PAGE_SIZE,
    offset,
  });
  const locale = i18n.language;

  function onSearch() {
    const trimmed = typed.trim();
    setPath(trimmed === "" ? undefined : trimmed);
    setOffset(0);
  }

  const columns: DataTableColumn<SourceDocument>[] = [
    {
      key: "document",
      header: t("sources.documents.columns.document"),
      cell: (item) => (
        <div className="flex flex-col">
          <span className="font-medium">{item.title}</span>
          {item.key !== item.title && (
            <span className="text-muted-foreground font-mono text-xs break-all">{item.key}</span>
          )}
        </div>
      ),
    },
    {
      key: "kind",
      header: t("sources.documents.columns.kind"),
      cell: (item) => t(`sources.documents.kinds.${item.kind}`),
    },
    {
      key: "language",
      header: t("sources.documents.columns.language"),
      cell: (item) => item.language ?? "—",
    },
    {
      key: "chunks",
      header: t("sources.documents.columns.chunks"),
      className: "text-right",
      cell: (item) => formatCount(item.chunk_count, locale),
    },
    {
      key: "indexedAt",
      header: t("sources.documents.columns.indexedAt"),
      cell: (item) =>
        item.indexed_at === null ? (
          t("sources.documents.notIndexed")
        ) : (
          <time dateTime={item.indexed_at}>
            {formatDateTime(new Date(item.indexed_at), locale)}
          </time>
        ),
    },
  ];

  return (
    <section aria-labelledby="source-documents" className="flex flex-col gap-3">
      <h2 id="source-documents" className="text-lg font-semibold">
        {t("sources.documents.title")}
      </h2>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor={pathId}>{t("sources.documents.path")}</Label>
          <Input
            id={pathId}
            type="search"
            className="w-full sm:w-72"
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor={kindId}>{t("sources.documents.kind")}</Label>
          <FilterSelect
            id={kindId}
            className="w-full sm:w-40"
            value={kind ?? ALL}
            options={[
              { value: ALL, label: t("sources.documents.kinds.all") },
              { value: "file", label: t("sources.documents.kinds.file") },
              { value: "commit", label: t("sources.documents.kinds.commit") },
            ]}
            onValueChange={(value) => {
              setKind(value === ALL ? undefined : (value as DocumentKind));
              setOffset(0);
            }}
          />
        </div>
        <Button type="submit" variant="outline">
          {t("sources.documents.search")}
        </Button>
      </form>
      {documents.data === undefined ? (
        documents.isPending ? (
          <p role="status" className="text-sm">
            {t("sources.documents.loading")}
          </p>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm">
              {t("sources.documents.loadFailed")}
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void documents.refetch();
              }}
            >
              {t("sources.retry")}
            </Button>
          </div>
        )
      ) : (
        <DataTable
          label={t("sources.documents.tableLabel")}
          columns={columns}
          rows={documents.data.items}
          rowKey={(item) => item.id}
          emptyMessage={t("sources.documents.empty")}
          busy={documents.isPlaceholderData}
          pagination={{
            offset,
            limit: DOCUMENTS_PAGE_SIZE,
            total: documents.data.total,
            onOffsetChange: setOffset,
          }}
        />
      )}
    </section>
  );
}
