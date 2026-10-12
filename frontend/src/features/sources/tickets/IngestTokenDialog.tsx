import { useState } from "react";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { translateApiError } from "@/i18n/apiErrors";
import type { Source } from "@/lib/api/sources";
import { type IngestToken, useRotateIngestToken } from "@/lib/api/tickets";

import { INGEST_TOKEN_VARIABLE } from "./ingestExamples";

interface IngestTokenDialogProps {
  workspaceId: string;
  source: Source;
}

/**
 * "Gerar token": warns that a current token stops working, then shows the new one (returned only
 * by this `POST`) with a copy button. Closing the dialog drops the token for good.
 */
export function IngestTokenDialog({ workspaceId, source }: IngestTokenDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [issued, setIssued] = useState<IngestToken | null>(null);
  const rotate = useRotateIngestToken(workspaceId);

  function onOpenChange(next: boolean) {
    setOpen(next);
    // On open and on close: the token never outlives the dialog.
    setIssued(null);
    rotate.reset();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" className="w-fit">
          {t("tickets.token.generate")}
        </Button>
      </DialogTrigger>
      <DialogContent showCloseButton={false} className="sm:max-w-xl">
        {issued === null ? (
          <>
            <DialogHeader>
              <DialogTitle>{t("tickets.token.confirmTitle", { name: source.name })}</DialogTitle>
              <DialogDescription>{t("tickets.token.confirmDescription")}</DialogDescription>
            </DialogHeader>
            {rotate.isError && <FormAlert message={translateApiError(rotate.error, t)} />}
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("tickets.token.cancel")}
                </Button>
              </DialogClose>
              <Button
                type="button"
                disabled={rotate.isPending}
                onClick={() => {
                  rotate.mutate(source.id, { onSuccess: setIssued });
                }}
              >
                {rotate.isPending ? t("tickets.token.generating") : t("tickets.token.confirm")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{t("tickets.token.issuedTitle")}</DialogTitle>
              <DialogDescription>
                {t("tickets.token.issuedDescription", { variable: INGEST_TOKEN_VARIABLE })}
              </DialogDescription>
            </DialogHeader>
            <section aria-labelledby="ingest-token-label" className="flex flex-col gap-2">
              <h3 id="ingest-token-label" className="text-sm font-medium">
                {t("tickets.token.label")}
              </h3>
              <code className="bg-muted rounded-md p-2 text-sm break-all">{issued.token}</code>
              <CopyButton text={issued.token} label={t("tickets.token.copy")} />
            </section>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button">{t("tickets.token.done")}</Button>
              </DialogClose>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
