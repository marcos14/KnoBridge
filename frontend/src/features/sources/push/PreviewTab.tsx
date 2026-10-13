import { type SyntheticEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/i18n/apiErrors";
import { ApiError } from "@/lib/api/client";
import { type IngestPreview, type PushSourceKind, usePreviewIngestItem } from "@/lib/api/tickets";

import { formatCount } from "../format";
import { itemProblems, parsePastedItem } from "./pushFormat";
import type { PushSource } from "./tabs";

interface PreviewTabProps {
  workspaceId: string;
  source: PushSource;
}

/**
 * Paste one ticket or card and see the Markdown the index would get with the source's current
 * settings, with the anonymization markers applied. Nothing is written.
 */
export function PreviewTab({ workspaceId, source }: PreviewTabProps) {
  const { t } = useTranslation();
  const fieldId = useId();
  const hintId = useId();
  const [text, setText] = useState("");
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const preview = usePreviewIngestItem(workspaceId);
  const kind = source.kind;
  const problems = preview.error instanceof ApiError ? itemProblems(preview.error.details) : [];

  function onSubmit(event: SyntheticEvent) {
    event.preventDefault();
    const pasted = parsePastedItem(text, kind);
    if (!pasted.ok) {
      setLocalProblem(
        pasted.reason === "invalidJson"
          ? t("ingest.preview.invalidJson")
          : t(`${kind}.preview.${pasted.reason}`),
      );
      preview.reset();
      return;
    }
    setLocalProblem(null);
    preview.mutate({ sourceId: source.id, item: pasted.item });
  }

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="ingest-preview-title" className="flex flex-col gap-3">
        <h2 id="ingest-preview-title" className="text-lg font-semibold">
          {t(`${kind}.preview.title`)}
        </h2>
        <p className="text-muted-foreground text-sm">{t(`${kind}.preview.description`)}</p>
        <form noValidate className="flex flex-col gap-3" onSubmit={onSubmit}>
          {localProblem !== null && <FormAlert message={localProblem} />}
          {preview.isError && (
            <div className="flex flex-col gap-1">
              <FormAlert message={translateApiError(preview.error, t)} />
              {problems.length > 0 && (
                <ul
                  aria-label={t(`${kind}.preview.problemsLabel`)}
                  className="text-muted-foreground font-mono text-xs"
                >
                  {problems.map((problem) => (
                    <li key={problem}>{problem}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor={fieldId}>{t(`${kind}.preview.item`)}</Label>
            <Textarea
              id={fieldId}
              rows={10}
              aria-describedby={hintId}
              className="font-mono text-xs"
              value={text}
              onChange={(event) => {
                setText(event.target.value);
              }}
            />
            <p id={hintId} className="text-muted-foreground text-sm">
              {t(`${kind}.preview.itemHint`)}
            </p>
          </div>
          <Button type="submit" className="w-fit" disabled={preview.isPending}>
            {preview.isPending ? t("ingest.preview.loading") : t("ingest.preview.submit")}
          </Button>
        </form>
      </section>
      {preview.data !== undefined && <PreviewResult kind={kind} result={preview.data} />}
    </div>
  );
}

/** Whether the preview kept the kind's extra text: internal notes of a ticket, comments of a card. */
function includesExtra(result: IngestPreview): boolean {
  return "include_comments" in result ? result.include_comments : result.include_internal_notes;
}

function PreviewResult({ kind, result }: { kind: PushSourceKind; result: IngestPreview }) {
  const { t, i18n } = useTranslation();
  return (
    <section aria-labelledby="ingest-preview-result" className="flex flex-col gap-3">
      <h2 id="ingest-preview-result" className="text-lg font-semibold">
        {t("ingest.preview.resultTitle", { title: result.title })}
      </h2>
      <p className="text-sm">
        {t(result.anonymize ? "ingest.preview.anonymized" : "ingest.preview.notAnonymized")}{" "}
        {t(includesExtra(result) ? `${kind}.preview.withExtra` : `${kind}.preview.withoutExtra`)}
      </p>
      {result.anonymize && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t("ingest.preview.markers")}</h3>
          {result.markers.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("ingest.preview.noMarkers")}</p>
          ) : (
            <ul aria-label={t("ingest.preview.markers")} className="flex flex-wrap gap-2">
              {result.markers.map((item) => (
                <li key={item.marker}>
                  <Badge variant="outline">
                    {t("ingest.preview.marker", {
                      marker: item.marker,
                      times: formatCount(item.count, i18n.language),
                    })}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <pre
        aria-label={t(`${kind}.preview.markdown`)}
        className="bg-muted overflow-x-auto rounded-md p-3 font-mono text-xs whitespace-pre-wrap"
      >
        {result.markdown}
      </pre>
    </section>
  );
}
