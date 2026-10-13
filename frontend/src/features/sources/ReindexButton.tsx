import { useId } from "react";
import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { isRunActive, type Source, useReindexSource } from "@/lib/api/sources";

import type { Feedback } from "./Feedback";

interface ReindexButtonProps {
  workspaceId: string;
  source: Source;
  onFeedback: (feedback: Feedback) => void;
}

/**
 * "Reindexar", after a confirmation saying that every document is processed again. A tickets
 * source cannot be reindexed (its raw tickets are deleted once indexed): the button stays disabled
 * with the reason next to it. Also disabled for an inactive source or while a sync runs.
 */
export function ReindexButton({ workspaceId, source, onFeedback }: ReindexButtonProps) {
  const { t } = useTranslation();
  const reasonId = useId();
  const reindex = useReindexSource(workspaceId);

  if (source.kind === "tickets") {
    return (
      <div className="flex flex-col items-start gap-1">
        <Button type="button" variant="outline" disabled aria-describedby={reasonId}>
          {t("sources.reindex")}
        </Button>
        <p id={reasonId} className="text-muted-foreground max-w-56 text-xs">
          {t("sources.reindexUnsupported")}
        </p>
      </div>
    );
  }

  return (
    <ConfirmDialog
      trigger={
        <Button
          type="button"
          variant="outline"
          disabled={reindex.isPending || !source.active || isRunActive(source.last_run?.status)}
        >
          {reindex.isPending ? t("sources.reindexing") : t("sources.reindex")}
        </Button>
      }
      title={t("sources.reindexTitle", { name: source.name })}
      description={t("sources.reindexDescription")}
      confirmLabel={t("sources.reindex")}
      destructive={false}
      onConfirm={() => {
        onFeedback(null);
        reindex.mutate(source.id, {
          onSuccess: () => {
            onFeedback({
              kind: "status",
              message: t("sources.reindexStarted", { name: source.name }),
            });
          },
          onError: (error) => {
            onFeedback({ kind: "alert", message: translateApiError(error, t) });
          },
        });
      }}
    />
  );
}
