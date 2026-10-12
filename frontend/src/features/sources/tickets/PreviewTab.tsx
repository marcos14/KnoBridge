import { type SyntheticEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { translateApiError } from "@/i18n/apiErrors";
import { ApiError } from "@/lib/api/client";
import type { Source } from "@/lib/api/sources";
import { type TicketPreview, usePreviewTicket } from "@/lib/api/tickets";

import { formatCount } from "../format";
import { parsePastedTicket, ticketProblems } from "./ticketFormat";

interface PreviewTabProps {
  workspaceId: string;
  source: Source;
}

/**
 * Paste one ticket and see the Markdown the index would get with the source's current settings,
 * with the anonymization markers applied. Nothing is written.
 */
export function PreviewTab({ workspaceId, source }: PreviewTabProps) {
  const { t } = useTranslation();
  const fieldId = useId();
  const hintId = useId();
  const [text, setText] = useState("");
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const preview = usePreviewTicket(workspaceId);
  const problems = preview.error instanceof ApiError ? ticketProblems(preview.error.details) : [];

  function onSubmit(event: SyntheticEvent) {
    event.preventDefault();
    const pasted = parsePastedTicket(text);
    if (!pasted.ok) {
      setLocalProblem(t(`tickets.preview.problems.${pasted.reason}`));
      preview.reset();
      return;
    }
    setLocalProblem(null);
    preview.mutate({ sourceId: source.id, ticket: pasted.ticket });
  }

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="ticket-preview-title" className="flex flex-col gap-3">
        <h2 id="ticket-preview-title" className="text-lg font-semibold">
          {t("tickets.preview.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("tickets.preview.description")}</p>
        <form noValidate className="flex flex-col gap-3" onSubmit={onSubmit}>
          {localProblem !== null && <FormAlert message={localProblem} />}
          {preview.isError && (
            <div className="flex flex-col gap-1">
              <FormAlert message={translateApiError(preview.error, t)} />
              {problems.length > 0 && (
                <ul
                  aria-label={t("tickets.preview.problemsLabel")}
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
            <Label htmlFor={fieldId}>{t("tickets.preview.ticket")}</Label>
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
              {t("tickets.preview.ticketHint")}
            </p>
          </div>
          <Button type="submit" className="w-fit" disabled={preview.isPending}>
            {preview.isPending ? t("tickets.preview.loading") : t("tickets.preview.submit")}
          </Button>
        </form>
      </section>
      {preview.data !== undefined && <PreviewResult result={preview.data} />}
    </div>
  );
}

function PreviewResult({ result }: { result: TicketPreview }) {
  const { t, i18n } = useTranslation();
  return (
    <section aria-labelledby="ticket-preview-result" className="flex flex-col gap-3">
      <h2 id="ticket-preview-result" className="text-lg font-semibold">
        {t("tickets.preview.resultTitle", { title: result.title })}
      </h2>
      <p className="text-sm">
        {t(result.anonymize ? "tickets.preview.anonymized" : "tickets.preview.notAnonymized")}{" "}
        {t(
          result.include_internal_notes
            ? "tickets.preview.withInternalNotes"
            : "tickets.preview.withoutInternalNotes",
        )}
      </p>
      {result.anonymize && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t("tickets.preview.markers")}</h3>
          {result.markers.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("tickets.preview.noMarkers")}</p>
          ) : (
            <ul aria-label={t("tickets.preview.markers")} className="flex flex-wrap gap-2">
              {result.markers.map((item) => (
                <li key={item.marker}>
                  <Badge variant="outline">
                    {t("tickets.preview.marker", {
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
        aria-label={t("tickets.preview.markdown")}
        className="bg-muted overflow-x-auto rounded-md p-3 font-mono text-xs whitespace-pre-wrap"
      >
        {result.markdown}
      </pre>
    </section>
  );
}
