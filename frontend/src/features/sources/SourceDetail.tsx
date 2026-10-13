import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { isApiErrorCode } from "@/lib/api/client";
import { type Collection, useCollections } from "@/lib/api/collections";
import { type Source, useSource, useTestSource } from "@/lib/api/sources";

import { DocumentsSection } from "./DocumentsSection";
import { type Feedback, FeedbackMessage } from "./Feedback";
import { RunnerSourceTabs } from "./harness/RunnerSourceTabs";
import { NextRun } from "./NextRun";
import { ReindexButton } from "./ReindexButton";
import { RunsSection } from "./RunsSection";
import { SourceDialog } from "./SourceDialog";
import { testFailureReason } from "./format";
import { sourceLocation } from "./sourceForm";
import { SyncButton } from "./SyncButton";
import { TicketsSourceTabs } from "./tickets/TicketsSourceTabs";
import { TicketsSummary } from "./tickets/TicketsSummary";

interface SourceDetailProps {
  workspaceId: string;
  sourceId: string;
  canManage: boolean;
  /** Owners and admins: issue the send token of a tickets source. */
  canManageTokens: boolean;
}

/**
 * One source: its settings and actions, then its runs with the errors of one of them and its
 * documents; a runner source shows them in tabs, next to its modules and harness jobs; a tickets
 * source, for those who manage it, next to the API integration, the upload and the preview.
 */
export function SourceDetail({
  workspaceId,
  sourceId,
  canManage,
  canManageTokens,
}: SourceDetailProps) {
  const { t } = useTranslation();
  const source = useSource(workspaceId, sourceId);
  const collections = useCollections(workspaceId);

  return (
    <div className="flex flex-col gap-6">
      <Link
        to={`/w/${workspaceId}/sources`}
        className="inline-flex w-fit items-center gap-1 text-sm underline-offset-4 hover:underline"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {t("sources.detail.back")}
      </Link>
      {/* A failed poll keeps the data on screen; only a first load that fails replaces it. */}
      {source.data !== undefined && collections.data !== undefined ? (
        <>
          <SourceHeader
            workspaceId={workspaceId}
            source={source.data}
            collections={collections.data}
            canManage={canManage}
          />
          {source.data.kind === "runner" ? (
            <RunnerSourceTabs
              workspaceId={workspaceId}
              source={source.data}
              canManage={canManage}
            />
          ) : source.data.kind === "tickets" && canManage ? (
            <TicketsSourceTabs
              workspaceId={workspaceId}
              source={source.data}
              canManageToken={canManageTokens}
            />
          ) : (
            <>
              <RunsSection workspaceId={workspaceId} sourceId={sourceId} />
              <DocumentsSection workspaceId={workspaceId} sourceId={sourceId} />
            </>
          )}
        </>
      ) : source.isPending || collections.isPending ? (
        <p role="status" className="text-sm">
          {t("sources.detail.loading")}
        </p>
      ) : isApiErrorCode(source.error, "source_not_found") ? (
        <h1 className="text-xl font-semibold">{t("sources.detail.notFound")}</h1>
      ) : (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("sources.detail.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void source.refetch();
              void collections.refetch();
            }}
          >
            {t("sources.retry")}
          </Button>
        </div>
      )}
    </div>
  );
}

interface SourceHeaderProps {
  workspaceId: string;
  source: Source;
  collections: readonly Collection[];
  canManage: boolean;
}

function SourceHeader({ workspaceId, source, collections, canManage }: SourceHeaderProps) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const test = useTestSource(workspaceId);
  const collection = collections.find((item) => item.id === source.collection_id);
  const branch = source.config.branch;

  function onTest() {
    setFeedback(null);
    test.mutate(source.id, {
      // `error` is null exactly when `ok` is true.
      onSuccess: ({ error }) => {
        setFeedback(
          error === null
            ? { kind: "status", message: t("sources.testOk", { name: source.name }) }
            : {
                kind: "alert",
                message: t("sources.testFailed", {
                  name: source.name,
                  reason: testFailureReason(error, t),
                }),
              },
        );
      },
      onError: (error) => {
        setFeedback({ kind: "alert", message: translateApiError(error, t) });
      },
    });
  }

  return (
    <section aria-labelledby="source-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 id="source-title" className="text-xl font-semibold">
              {source.name}
            </h1>
            {!source.active && <Badge variant="outline">{t("sources.inactive")}</Badge>}
          </div>
          <p className="text-muted-foreground text-sm">
            {t("sources.detail.summary", {
              kind: t(`sources.kinds.${source.kind}`),
              collection: collection?.name,
            })}
          </p>
          {source.kind === "tickets" ? (
            <TicketsSummary source={source} />
          ) : source.kind === "cards" ? (
            <p className="text-muted-foreground text-sm">{t("sources.detail.cardsByApi")}</p>
          ) : (
            <p className="text-sm break-all">
              {source.kind === "runner"
                ? t("sources.detail.repository", { repository: sourceLocation(source) })
                : t("sources.detail.location", { location: sourceLocation(source) })}
            </p>
          )}
          {typeof branch === "string" && (
            <p className="text-sm">{t("sources.detail.branch", { branch })}</p>
          )}
          {source.include_globs.length > 0 && (
            <p className="text-sm">
              {t("sources.detail.include", { globs: source.include_globs.join(", ") })}
            </p>
          )}
          {source.exclude_globs.length > 0 && (
            <p className="text-sm">
              {t("sources.detail.exclude", { globs: source.exclude_globs.join(", ") })}
            </p>
          )}
          <p className="text-sm">
            {t("sources.detail.documentCount", { count: source.document_count })}
          </p>
          <div className="flex flex-wrap items-baseline gap-2 text-sm">
            <span>{t("sources.columns.nextRun")}:</span>
            <NextRun source={source} />
          </div>
        </div>
        {canManage && (
          <div className="flex flex-wrap items-start gap-2">
            <Button type="button" variant="outline" disabled={test.isPending} onClick={onTest}>
              {test.isPending ? t("sources.testing") : t("sources.test")}
            </Button>
            <SyncButton workspaceId={workspaceId} source={source} onFeedback={setFeedback} />
            <ReindexButton workspaceId={workspaceId} source={source} onFeedback={setFeedback} />
            {/* The panel does not edit a cards source yet: it is managed through the API. */}
            {source.kind !== "cards" && (
              <SourceDialog
                workspaceId={workspaceId}
                source={source}
                collections={collections}
                trigger={
                  <Button
                    type="button"
                    variant="outline"
                    aria-label={t("sources.editLabel", { name: source.name })}
                  >
                    {t("sources.edit")}
                  </Button>
                }
                onSaved={(saved) => {
                  setFeedback({
                    kind: "status",
                    message: t("sources.updated", { name: saved.name }),
                  });
                }}
              />
            )}
          </div>
        )}
      </div>
      <FeedbackMessage feedback={feedback} />
    </section>
  );
}
