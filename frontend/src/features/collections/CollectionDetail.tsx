import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { isApiErrorCode } from "@/lib/api/client";
import { type Collection, useCollection } from "@/lib/api/collections";
import { useProviders } from "@/lib/api/providers";

import { CollectionDialog } from "./CollectionDialog";
import { CollectionSources } from "./CollectionSources";
import { embeddingProviders } from "./collectionForm";
import { SearchPanel } from "./SearchPanel";

interface CollectionDetailProps {
  workspaceId: string;
  collectionId: string;
  canManage: boolean;
}

/** One collection: its embedding model and counts, its sources and the search test. */
export function CollectionDetail({ workspaceId, collectionId, canManage }: CollectionDetailProps) {
  const { t } = useTranslation();
  const collection = useCollection(workspaceId, collectionId);

  return (
    <div className="flex flex-col gap-6">
      <Link
        to={`/w/${workspaceId}/collections`}
        className="inline-flex w-fit items-center gap-1 text-sm underline-offset-4 hover:underline"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {t("collections.detail.back")}
      </Link>
      {collection.isPending ? (
        <p role="status" className="text-sm">
          {t("collections.detail.loading")}
        </p>
      ) : collection.isError ? (
        isApiErrorCode(collection.error, "not_found") ? (
          <h1 className="text-xl font-semibold">{t("collections.detail.notFound")}</h1>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm">
              {t("collections.detail.loadFailed")}
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void collection.refetch();
              }}
            >
              {t("collections.retry")}
            </Button>
          </div>
        )
      ) : (
        <>
          <CollectionHeader
            workspaceId={workspaceId}
            collection={collection.data}
            canManage={canManage}
          />
          <CollectionSources workspaceId={workspaceId} collectionId={collectionId} />
          <SearchPanel workspaceId={workspaceId} collectionId={collectionId} />
        </>
      )}
    </div>
  );
}

interface CollectionHeaderProps {
  workspaceId: string;
  collection: Collection;
  canManage: boolean;
}

function CollectionHeader({ workspaceId, collection, canManage }: CollectionHeaderProps) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">{collection.name}</h1>
          {collection.description !== "" && (
            <p className="text-muted-foreground text-sm">{collection.description}</p>
          )}
          <p className="text-sm">
            {t("collections.detail.embedding", { model: collection.embedding_model })}
          </p>
          <p className="text-sm">
            {t("collections.detail.counts", {
              sources: collection.source_count,
              documents: collection.document_count,
              chunks: collection.chunk_count,
            })}
          </p>
        </div>
        {canManage && (
          <EditCollection
            workspaceId={workspaceId}
            collection={collection}
            onSaved={(item) => {
              setSaved(t("collections.updated", { name: item.name }));
            }}
          />
        )}
      </div>
      {saved !== null && (
        <p role="status" className="text-sm">
          {saved}
        </p>
      )}
    </div>
  );
}

interface EditCollectionProps {
  workspaceId: string;
  collection: Collection;
  onSaved: (collection: Collection) => void;
}

/** "Editar", for managers only: the credentials come from a listing viewers may not read. */
function EditCollection({ workspaceId, collection, onSaved }: EditCollectionProps) {
  const { t } = useTranslation();
  const providers = useProviders(workspaceId);

  return (
    <CollectionDialog
      workspaceId={workspaceId}
      collection={collection}
      providers={embeddingProviders(providers.data ?? [])}
      trigger={
        <Button
          type="button"
          variant="outline"
          disabled={!providers.isSuccess}
          aria-label={t("collections.editLabel", { name: collection.name })}
        >
          {t("collections.edit")}
        </Button>
      }
      onSaved={onSaved}
    />
  );
}
