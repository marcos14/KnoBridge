import { type SyntheticEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/i18n/apiErrors";
import type { Source } from "@/lib/api/sources";
import { useUploadTickets } from "@/lib/api/tickets";

import { MAX_UPLOAD_BYTES, UPLOAD_EXTENSIONS, uploadFileProblem } from "./ticketFormat";
import { UploadReport } from "./UploadReport";

interface UploadTabProps {
  workspaceId: string;
  source: Source;
}

/**
 * Sends a `.json` or `.jsonl` export of tickets (same items as the API, or bare tickets) and shows
 * the report: counts, what happened to the sync and the rejected items line by line.
 */
export function UploadTab({ workspaceId, source }: UploadTabProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const hintId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [localProblem, setLocalProblem] = useState<string | null>(null);
  const upload = useUploadTickets(workspaceId);

  function onSubmit(event: SyntheticEvent) {
    event.preventDefault();
    if (file === null) {
      setLocalProblem(t("tickets.upload.problems.missing"));
      return;
    }
    const problem = uploadFileProblem(file);
    if (problem !== null) {
      setLocalProblem(
        t(`tickets.upload.problems.${problem}`, {
          extensions: UPLOAD_EXTENSIONS.join(", "),
          max: MAX_UPLOAD_BYTES / (1024 * 1024),
        }),
      );
      return;
    }
    setLocalProblem(null);
    upload.mutate({ sourceId: source.id, file });
  }

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="ticket-upload-title" className="flex flex-col gap-3">
        <h2 id="ticket-upload-title" className="text-lg font-semibold">
          {t("tickets.upload.title")}
        </h2>
        <p className="text-muted-foreground text-sm">{t("tickets.upload.description")}</p>
        {!source.active && <p className="text-sm">{t("tickets.upload.inactive")}</p>}
        <form noValidate className="flex flex-col gap-3" onSubmit={onSubmit}>
          {localProblem !== null && <FormAlert message={localProblem} />}
          {localProblem === null && upload.isError && (
            <FormAlert message={translateApiError(upload.error, t)} />
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor={inputId}>{t("tickets.upload.file")}</Label>
            <Input
              id={inputId}
              type="file"
              accept={UPLOAD_EXTENSIONS.join(",")}
              aria-describedby={hintId}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setLocalProblem(null);
                upload.reset();
              }}
            />
            <p id={hintId} className="text-muted-foreground text-sm">
              {t("tickets.upload.fileHint", { max: MAX_UPLOAD_BYTES / (1024 * 1024) })}
            </p>
          </div>
          <Button type="submit" className="w-fit" disabled={upload.isPending}>
            {upload.isPending ? t("tickets.upload.sending") : t("tickets.upload.submit")}
          </Button>
        </form>
      </section>
      {upload.data !== undefined && <UploadReport report={upload.data} />}
    </div>
  );
}
