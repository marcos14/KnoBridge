import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import type { CollectionSync } from "@/lib/api/collections";
import { type Source, useSyncCollection } from "@/lib/api/sources";

interface SyncAllButtonProps {
  workspaceId: string;
  collectionId: string;
  /** Sources of the collection, to name the skipped ones; empty disables the button. */
  sources: readonly Source[];
}

/**
 * "Sincronizar todas" (owner, admin or editor): starts a sync of every active source of the
 * collection, then says how many started and which were skipped and why.
 */
export function SyncAllButton({ workspaceId, collectionId, sources }: SyncAllButtonProps) {
  const { t } = useTranslation();
  const sync = useSyncCollection(workspaceId);
  const [result, setResult] = useState<CollectionSync | null>(null);
  const names = new Map(sources.map((item) => [item.id, item.name] as const));

  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        className="w-fit"
        disabled={sync.isPending || sources.length === 0}
        onClick={() => {
          setResult(null);
          sync.mutate(collectionId, { onSuccess: setResult });
        }}
      >
        {sync.isPending ? t("collections.detail.syncingAll") : t("collections.detail.syncAll")}
      </Button>
      {sync.isError && <FormAlert message={translateApiError(sync.error, t)} />}
      {result !== null && (
        <div role="status" className="flex flex-col gap-1 text-sm">
          <p>{t("collections.detail.syncAllStarted", { count: result.started.length })}</p>
          {result.skipped.length > 0 && (
            <>
              <p>{t("collections.detail.syncAllSkipped", { count: result.skipped.length })}</p>
              <ul className="list-disc pl-5">
                {result.skipped.map((item) => (
                  <li key={item.source_id}>
                    {t("collections.detail.skippedSource", {
                      name: names.get(item.source_id) ?? item.source_id,
                      reason: t(`collections.detail.skipReasons.${item.reason}`),
                    })}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
