import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { isRunActive, type Source, useCancelSync, useSyncSource } from "@/lib/api/sources";

import type { Feedback } from "./Feedback";

interface SyncButtonProps {
  workspaceId: string;
  source: Source;
  size?: "sm" | "default";
  onFeedback: (feedback: Feedback) => void;
}

/**
 * "Sincronizar agora", or "Cancelar sincronização" (after a confirmation) while the last run is
 * queued or running. The reload after either starts (or ends) the polling of the screen.
 */
export function SyncButton({ workspaceId, source, size = "default", onFeedback }: SyncButtonProps) {
  const { t } = useTranslation();
  const sync = useSyncSource(workspaceId);
  const cancel = useCancelSync(workspaceId);
  const running = isRunActive(source.last_run?.status);
  const busy = sync.isPending || cancel.isPending;
  const callbacks = (key: "sources.syncStarted" | "sources.cancelRequested") => ({
    onSuccess: () => {
      onFeedback({ kind: "status", message: t(key, { name: source.name }) });
    },
    onError: (error: unknown) => {
      onFeedback({ kind: "alert", message: translateApiError(error, t) });
    },
  });

  return running ? (
    <ConfirmDialog
      trigger={
        <Button
          type="button"
          variant="outline"
          size={size}
          disabled={busy}
          aria-label={t("sources.cancelLabel", { name: source.name })}
        >
          {t("sources.cancel")}
        </Button>
      }
      title={t("sources.cancelTitle", { name: source.name })}
      description={t("sources.cancelDescription")}
      confirmLabel={t("sources.cancel")}
      onConfirm={() => {
        onFeedback(null);
        cancel.mutate(source.id, callbacks("sources.cancelRequested"));
      }}
    />
  ) : (
    <Button
      type="button"
      size={size}
      disabled={busy || !source.active}
      aria-label={t("sources.syncLabel", { name: source.name })}
      onClick={() => {
        onFeedback(null);
        sync.mutate(source.id, callbacks("sources.syncStarted"));
      }}
    >
      {t("sources.sync")}
    </Button>
  );
}
