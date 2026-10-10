import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { translateApiError } from "@/i18n/apiErrors";
import { type Assistant, useAssistants, useDeleteAssistant } from "@/lib/api/assistants";
import { useProviders } from "@/lib/api/providers";
import { clampOffset, pageOf } from "@/lib/pagination";

import { AssistantDialog } from "./AssistantDialog";

/** Rows per page of the assistant table (paged in the browser). */
export const ASSISTANTS_PAGE_SIZE = 20;

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
        <AssistantsList key={workspace.id} workspaceId={workspace.id} />
      ) : (
        <h1 className="text-xl font-semibold">{t("assistants.title")}</h1>
      )}
    </div>
  );
}

function AssistantsList({ workspaceId }: { workspaceId: string }) {
  const { t } = useTranslation();
  const [requestedOffset, setRequestedOffset] = useState(0);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const assistants = useAssistants(workspaceId);
  const providers = useProviders(workspaceId);
  const remove = useDeleteAssistant(workspaceId);

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
  if (assistants.isError || providers.isError) {
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

  const all = assistants.data;
  const providerList = providers.data;
  const providerNames = new Map(providerList.map((item) => [item.id, item.name] as const));
  const offset = clampOffset(requestedOffset, ASSISTANTS_PAGE_SIZE, all.length);
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
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                aria-label={t("assistants.editLabel", { name: item.name })}
              >
                {t("assistants.edit")}
              </Button>
            }
            onSaved={showSaved("assistants.updated")}
          />
          <ConfirmDialog
            trigger={
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={remove.isPending}
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
      <DataTable
        label={t("assistants.tableLabel")}
        columns={columns}
        rows={pageOf(all, offset, ASSISTANTS_PAGE_SIZE)}
        rowKey={(item) => item.id}
        emptyMessage={t("assistants.empty")}
        pagination={{
          offset,
          limit: ASSISTANTS_PAGE_SIZE,
          total: all.length,
          onOffsetChange: setRequestedOffset,
        }}
      />
    </>
  );
}
