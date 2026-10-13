import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { ListToolbar } from "@/components/ListToolbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { useListSearch } from "@/hooks/use-list-search";
import { useOffsetClamp } from "@/hooks/use-offset-clamp";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type Assistant,
  useAssistantPage,
  useDeleteAssistant,
  useDuplicateAssistant,
} from "@/lib/api/assistants";
import { useCollections } from "@/lib/api/collections";
import { useProviders } from "@/lib/api/providers";
import {
  booleanFilter,
  hasListCriteria,
  isBooleanFilter,
  type ListSearchSpec,
  sortLabelKey,
} from "@/lib/listSearch";
import { canManageWorkspace } from "@/lib/roles";
import { isUuid } from "@/lib/uuid";

import { AssistantDialog } from "./AssistantDialog";

/** Rows per page of the assistant table (paged by the API). */
export const ASSISTANTS_PAGE_SIZE = 20;

const ASSISTANT_SORTS = ["name", "-name", "-created_at", "-updated_at"] as const;

/** Search, filters and sort of the list, in the URL. */
const ASSISTANT_LIST: ListSearchSpec<
  "active" | "provider" | "collection",
  (typeof ASSISTANT_SORTS)[number]
> = {
  filters: { active: isBooleanFilter, provider: isUuid, collection: isUuid },
  sorts: ASSISTANT_SORTS,
};

type Feedback = { kind: "status" | "alert"; message: string } | null;

/**
 * `/w/:workspaceId/assistants` (owner, admin or editor): the workspace's assistants with their
 * status. Create, edit and delete (deleting also deletes the assistant's conversations).
 */
export function AssistantsPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-5xl flex-col gap-6">
      {workspace !== undefined ? (
        <AssistantsList
          key={workspace.id}
          workspaceId={workspace.id}
          canManageSecret={canManageWorkspace(workspace.role)}
        />
      ) : (
        <h1 className="text-xl font-semibold">{t("assistants.title")}</h1>
      )}
    </div>
  );
}

function AssistantsList({
  workspaceId,
  canManageSecret,
}: {
  workspaceId: string;
  canManageSecret: boolean;
}) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  // The copy just made by "Duplicar", whose edit dialog opens at once.
  const [copy, setCopy] = useState<Assistant | null>(null);
  const { search, setQuery, setFilter, setSort, setOffset, clear } = useListSearch(ASSISTANT_LIST);
  const { filters } = search;
  const assistants = useAssistantPage(workspaceId, {
    query: search.query === "" ? undefined : search.query,
    active: booleanFilter(filters.active),
    provider_id: filters.provider,
    collection_id: filters.collection,
    sort: search.sort,
    limit: ASSISTANTS_PAGE_SIZE,
    offset: search.offset,
  });
  useOffsetClamp(search.offset, ASSISTANTS_PAGE_SIZE, assistants.data?.total, setOffset);
  const providers = useProviders(workspaceId);
  // Only names for the collection filter: while they load (or if they fail) it offers none.
  const collections = useCollections(workspaceId);
  const remove = useDeleteAssistant(workspaceId);
  const duplicate = useDuplicateAssistant(workspaceId);
  const busy = remove.isPending || duplicate.isPending;

  function onDuplicate(assistant: Assistant) {
    setFeedback(null);
    duplicate.mutate(assistant.id, {
      onSuccess: (created) => {
        setFeedback({
          kind: "status",
          message: t("assistants.duplicated", { name: created.name }),
        });
        setCopy(created);
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  function onDelete(assistant: Assistant) {
    setFeedback(null);
    remove.mutate(assistant.id, {
      onSuccess: () => {
        setFeedback({ kind: "status", message: t("assistants.deleted", { name: assistant.name }) });
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  const title = (
    <div className="flex flex-col gap-1">
      <h1 className="text-xl font-semibold">{t("assistants.title")}</h1>
      <p className="text-muted-foreground text-sm">{t("assistants.description")}</p>
    </div>
  );

  if (assistants.isPending || providers.isPending) {
    return (
      <>
        {title}
        <p role="status" className="text-sm">
          {t("assistants.loading")}
        </p>
      </>
    );
  }
  if (assistants.data === undefined || providers.isError) {
    return (
      <>
        {title}
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("assistants.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void assistants.refetch();
              void providers.refetch();
            }}
          >
            {t("assistants.retry")}
          </Button>
        </div>
      </>
    );
  }

  const { items, total } = assistants.data;
  const providerList = providers.data;
  const providerNames = new Map(providerList.map((item) => [item.id, item.name] as const));
  const criteria = hasListCriteria(search);
  const filter = (key: keyof typeof filters) => ({
    key,
    value: filters[key],
    onChange: (value: string | undefined) => {
      setFilter(key, value);
    },
  });
  const showSaved = (key: "assistants.created" | "assistants.updated") => (saved: Assistant) => {
    setFeedback({ kind: "status", message: t(key, { name: saved.name }) });
  };
  const columns: DataTableColumn<Assistant>[] = [
    {
      key: "name",
      header: t("assistants.columns.name"),
      cell: (item) => (
        <div className="flex flex-col">
          <span>{item.name}</span>
          {item.description !== "" && (
            <span className="text-muted-foreground text-sm">{item.description}</span>
          )}
        </div>
      ),
    },
    {
      key: "model",
      header: t("assistants.columns.model"),
      cell: (item) =>
        [providerNames.get(item.provider_id), item.model]
          .filter((part) => part !== undefined)
          .join(" · "),
    },
    {
      key: "collections",
      header: t("assistants.columns.collections"),
      cell: (item) =>
        item.collection_ids.length > 0 ? (
          String(item.collection_ids.length)
        ) : (
          <span className="text-muted-foreground">{t("assistants.noCollections")}</span>
        ),
    },
    {
      key: "status",
      header: t("assistants.columns.status"),
      cell: (item) =>
        item.active ? (
          <Badge>{t("assistants.active")}</Badge>
        ) : (
          <Badge variant="secondary">{t("assistants.inactive")}</Badge>
        ),
    },
    {
      key: "actions",
      header: t("assistants.columns.actions"),
      cell: (item) => (
        <div className="flex flex-wrap gap-2">
          <AssistantDialog
            workspaceId={workspaceId}
            assistant={item}
            providers={providerList}
            canManageSecret={canManageSecret}
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                aria-label={t("assistants.editLabel", { name: item.name })}
              >
                {t("assistants.edit")}
              </Button>
            }
            onSaved={showSaved("assistants.updated")}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            aria-label={t("assistants.duplicateLabel", { name: item.name })}
            onClick={() => {
              onDuplicate(item);
            }}
          >
            {duplicate.isPending && duplicate.variables === item.id
              ? t("assistants.duplicating")
              : t("assistants.duplicate")}
          </Button>
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                aria-label={t("assistants.deleteLabel", { name: item.name })}
              >
                {t("assistants.delete")}
              </Button>
            }
            title={t("assistants.deleteTitle", { name: item.name })}
            description={t("assistants.deleteDescription")}
            confirmLabel={t("assistants.delete")}
            onConfirm={() => {
              onDelete(item);
            }}
          />
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-4">
        {title}
        {providerList.length > 0 && (
          <AssistantDialog
            workspaceId={workspaceId}
            providers={providerList}
            canManageSecret={canManageSecret}
            trigger={<Button type="button">{t("assistants.create")}</Button>}
            onSaved={showSaved("assistants.created")}
          />
        )}
      </div>
      {providerList.length === 0 && (
        <p className="text-sm">
          {t("assistants.needProvider")}{" "}
          <Link to={`/w/${workspaceId}/providers`} className="underline underline-offset-4">
            {t("assistants.goToProviders")}
          </Link>
        </p>
      )}
      {feedback?.kind === "alert" && (
        <FormAlert key={feedback.message} message={feedback.message} />
      )}
      {feedback?.kind === "status" && (
        <p role="status" className="text-sm">
          {feedback.message}
        </p>
      )}
      <ListToolbar
        searchLabel={t("assistants.search")}
        searchPlaceholder={t("assistants.searchPlaceholder")}
        query={search.query}
        onQueryChange={setQuery}
        filters={[
          {
            ...filter("active"),
            label: t("assistants.columns.status"),
            allLabel: t("listToolbar.allStatuses"),
            options: [
              { value: "true", label: t("listToolbar.activeOnly") },
              { value: "false", label: t("listToolbar.inactiveOnly") },
            ],
          },
          {
            ...filter("provider"),
            label: t("assistants.providerFilter"),
            allLabel: t("assistants.allProviders"),
            options: providerList.map((item) => ({ value: item.id, label: item.name })),
          },
          {
            ...filter("collection"),
            label: t("assistants.columns.collections"),
            allLabel: t("assistants.allCollections"),
            options: (collections.data ?? []).map((item) => ({ value: item.id, label: item.name })),
          },
        ]}
        sort={{
          value: search.sort,
          options: ASSISTANT_SORTS.map((sort) => ({ value: sort, label: t(sortLabelKey(sort)) })),
          onChange: setSort,
        }}
        onClear={criteria ? clear : undefined}
      />
      <DataTable
        label={t("assistants.tableLabel")}
        columns={columns}
        rows={items}
        rowKey={(item) => item.id}
        emptyMessage={
          criteria ? (
            t("listToolbar.noResults")
          ) : providerList.length > 0 ? (
            <>
              {t("assistants.emptyNext")}{" "}
              <Link to={`/w/${workspaceId}/collections`} className="underline underline-offset-4">
                {t("assistants.goToCollections")}
              </Link>
            </>
          ) : (
            t("assistants.empty")
          )
        }
        busy={assistants.isPlaceholderData}
        pagination={{
          offset: search.offset,
          limit: ASSISTANTS_PAGE_SIZE,
          total,
          onOffsetChange: setOffset,
        }}
      />
      {copy !== null && (
        <AssistantDialog
          key={copy.id}
          workspaceId={workspaceId}
          assistant={copy}
          providers={providerList}
          canManageSecret={canManageSecret}
          defaultOpen
          onClosed={() => {
            setCopy(null);
          }}
          onSaved={showSaved("assistants.updated")}
        />
      )}
    </>
  );
}
