import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { useAssistants } from "@/lib/api/assistants";
import { useMembers } from "@/lib/api/members";
import {
  useConversationStats,
  useWorkspaceConversations,
  type WorkspaceConversation,
} from "@/lib/api/workspaceConversations";
import {
  hasConversationFilters,
  toConversationsQuery,
  toCreationPeriod,
} from "@/lib/conversationFilters";
import { formatDateTime } from "@/lib/intl";

import { ConversationFilterBar } from "./ConversationFilterBar";
import { conversationOwner } from "./conversationOwner";
import { ConversationStatsCards } from "./ConversationStatsCards";
import { useConversationSearch } from "./useConversationSearch";

/** Rows per page of the conversations table (paged by the API). */
const CONVERSATIONS_TABLE_PAGE_SIZE = 20;

/** Totals of the period, the filters (in the URL) and the page of conversations. */
export function ConversationsOverview({ workspaceId }: { workspaceId: string }) {
  const { t, i18n } = useTranslation();
  const { search: query } = useLocation();
  const { search, setFilters, setOffset } = useConversationSearch();
  const conversations = useWorkspaceConversations(
    workspaceId,
    toConversationsQuery(search, CONVERSATIONS_TABLE_PAGE_SIZE),
  );
  const stats = useConversationStats(workspaceId, toCreationPeriod(search.filters));
  // Both fill the filters; while they load, a filter from a shared link shows its id.
  const assistants = useAssistants(workspaceId);
  const members = useMembers(workspaceId);

  const columns: DataTableColumn<WorkspaceConversation>[] = [
    {
      key: "title",
      header: t("conversations.columns.title"),
      cell: (row) => (
        <Link
          to={{ pathname: `/w/${workspaceId}/conversations/${row.id}`, search: query }}
          className="font-medium underline-offset-4 hover:underline"
        >
          {row.title ?? t("conversations.untitled")}
        </Link>
      ),
    },
    {
      key: "user",
      header: t("conversations.columns.user"),
      cell: (row) => {
        const owner = conversationOwner(row, t);
        return (
          <div className="flex flex-col">
            <span>{owner.name}</span>
            <span className="text-muted-foreground text-xs">{owner.detail}</span>
          </div>
        );
      },
    },
    {
      key: "assistant",
      header: t("conversations.columns.assistant"),
      cell: (row) => row.product_name,
    },
    {
      key: "messages",
      header: t("conversations.columns.messages"),
      className: "text-right",
      cell: (row) => row.message_count.toLocaleString(i18n.language),
    },
    {
      key: "feedback",
      header: t("conversations.columns.feedback"),
      cell: (row) => (
        <span
          aria-label={t("conversations.feedbackLabel", {
            up: row.thumbs_up,
            down: row.thumbs_down,
          })}
        >
          {t("conversations.feedbackSummary", { up: row.thumbs_up, down: row.thumbs_down })}
        </span>
      ),
    },
    {
      key: "lastActivity",
      header: t("conversations.columns.lastActivity"),
      cell: (row) =>
        row.last_message_at === null ? (
          t("conversations.noActivity")
        ) : (
          <time dateTime={row.last_message_at}>
            {formatDateTime(new Date(row.last_message_at), i18n.language)}
          </time>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <ConversationStatsCards stats={stats} />
      <ConversationFilterBar
        filters={search.filters}
        assistants={(assistants.data ?? []).map(({ id, name }) => ({ id, name }))}
        users={(members.data ?? []).map(({ user_id: id, name }) => ({ id, name }))}
        onChange={setFilters}
      />
      {conversations.isPending ? (
        <p role="status" className="text-sm">
          {t("conversations.loading")}
        </p>
      ) : conversations.isError ? (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("conversations.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void conversations.refetch();
            }}
          >
            {t("conversations.retry")}
          </Button>
        </div>
      ) : (
        <DataTable
          label={t("conversations.tableLabel")}
          columns={columns}
          rows={conversations.data.items}
          rowKey={(row) => row.id}
          emptyMessage={
            hasConversationFilters(search.filters)
              ? t("conversations.emptyFiltered")
              : t("conversations.empty")
          }
          busy={conversations.isPlaceholderData}
          pagination={{
            offset: search.offset,
            limit: CONVERSATIONS_TABLE_PAGE_SIZE,
            total: conversations.data.total,
            onOffsetChange: setOffset,
          }}
        />
      )}
    </div>
  );
}
