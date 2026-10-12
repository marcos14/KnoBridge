import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { auditActionLabel } from "@/i18n/auditActions";
import type { AuditEvent } from "@/lib/api/audit";
import type { components } from "@/lib/api/schema.gen";
import { hasAuditFilters } from "@/lib/auditFilters";
import { formatDateTime } from "@/lib/intl";

import { actorLabel, type AuditActor } from "./actors";
import { AuditEventDialog } from "./AuditEventDialog";
import { AuditFilterBar } from "./AuditFilterBar";
import { useAuditSearch } from "./useAuditSearch";

type AuditEventPage = components["schemas"]["AuditEventPage"];

/** Rows per page of the audit tables (paged by the API). */
export const AUDIT_PAGE_SIZE = 20;

interface AuditLogProps {
  /** The page of events for the filters in the URL (`useAuditSearch`). */
  events: UseQueryResult<AuditEventPage>;
  actors: readonly AuditActor[];
}

/**
 * Audit trail with filters kept in the URL, server paging and the detail of each event. Shared by
 * the workspace and the instance screens, which only differ in where the events come from.
 */
export function AuditLog({ events, actors }: AuditLogProps) {
  const { t, i18n } = useTranslation();
  const { search, setFilters, setOffset } = useAuditSearch();
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const actorOf = (event: AuditEvent) => actorLabel(event.actor_user_id, actors, t);

  const columns: DataTableColumn<AuditEvent>[] = [
    {
      key: "occurredAt",
      header: t("audit.columns.occurredAt"),
      cell: (event) => (
        <time dateTime={event.occurred_at}>
          {formatDateTime(new Date(event.occurred_at), i18n.language)}
        </time>
      ),
    },
    {
      key: "action",
      header: t("audit.columns.action"),
      cell: (event) => auditActionLabel(event.action, t),
    },
    { key: "actor", header: t("audit.columns.actor"), cell: actorOf },
    {
      key: "target",
      header: t("audit.columns.target"),
      cell: (event) => event.target_type ?? t("audit.detail.none"),
    },
    {
      key: "details",
      header: t("audit.columns.details"),
      cell: (event) => (
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t("audit.viewLabel", {
            action: auditActionLabel(event.action, t),
            when: formatDateTime(new Date(event.occurred_at), i18n.language),
          })}
          onClick={() => {
            setSelected(event);
          }}
        >
          {t("audit.view")}
        </Button>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <AuditFilterBar filters={search.filters} actors={actors} onChange={setFilters} />
      {events.isPending ? (
        <p role="status" className="text-sm">
          {t("audit.loading")}
        </p>
      ) : events.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("audit.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void events.refetch();
            }}
          >
            {t("audit.retry")}
          </Button>
        </div>
      ) : (
        <DataTable
          label={t("audit.tableLabel")}
          columns={columns}
          rows={events.data.items}
          rowKey={(event) => event.id}
          emptyMessage={
            hasAuditFilters(search.filters) ? t("audit.emptyFiltered") : t("audit.empty")
          }
          busy={events.isPlaceholderData}
          pagination={{
            offset: search.offset,
            limit: AUDIT_PAGE_SIZE,
            total: events.data.total,
            onOffsetChange: setOffset,
          }}
        />
      )}
      <AuditEventDialog
        event={selected}
        actor={selected === null ? "" : actorOf(selected)}
        onClose={() => {
          setSelected(null);
        }}
      />
    </div>
  );
}
