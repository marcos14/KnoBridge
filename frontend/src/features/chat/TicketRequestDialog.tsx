import { zodResolver } from "@hookform/resolvers/zod";
import type { UseMutationResult } from "@tanstack/react-query";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type TicketRequestPreview,
  type TicketRequestTarget,
  useCreateTicketRequest,
} from "@/lib/api/ticketRequests";

import { ticketSummarySchema, type TicketSummaryValues } from "./chatForm";

export type TicketPreviewMutation = UseMutationResult<
  TicketRequestPreview,
  Error,
  TicketRequestTarget
>;

interface TicketRequestDialogProps {
  workspaceId: string;
  conversationId: string;
  /** The answer a ticket is asked for; `null` keeps the dialog closed. */
  messageId: string | null;
  /** The preview of that answer, asked for by whoever opened the dialog. */
  preview: TicketPreviewMutation;
  onClose: () => void;
}

/**
 * "Abrir chamado": shows what will be sent (the question, the summary the member can edit, who
 * asks and how many messages go along) and sends it only on confirmation.
 */
export function TicketRequestDialog({
  workspaceId,
  conversationId,
  messageId,
  preview,
  onClose,
}: TicketRequestDialogProps) {
  const { t } = useTranslation();

  let body;
  if (preview.isError) {
    body = (
      <>
        <FormAlert message={translateApiError(preview.error, t)} />
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              {t("chat.ticket.close")}
            </Button>
          </DialogClose>
        </DialogFooter>
      </>
    );
  } else if (preview.isSuccess && messageId !== null) {
    body = (
      <TicketRequestForm
        key={messageId}
        workspaceId={workspaceId}
        target={{ conversationId, messageId }}
        preview={preview.data}
        onSent={onClose}
      />
    );
  } else {
    body = (
      <>
        <p role="status" className="text-sm">
          {t("chat.ticket.preparing")}
        </p>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              {t("chat.ticket.cancel")}
            </Button>
          </DialogClose>
        </DialogFooter>
      </>
    );
  }

  return (
    <Dialog
      open={messageId !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("chat.ticket.title")}</DialogTitle>
          <DialogDescription>{t("chat.ticket.description")}</DialogDescription>
        </DialogHeader>
        {body}
      </DialogContent>
    </Dialog>
  );
}

interface TicketRequestFormProps {
  workspaceId: string;
  target: TicketRequestTarget;
  preview: TicketRequestPreview;
  onSent: () => void;
}

function TicketRequestForm({ workspaceId, target, preview, onSent }: TicketRequestFormProps) {
  const { t } = useTranslation();
  const create = useCreateTicketRequest(workspaceId);
  const schema = useMemo(() => ticketSummarySchema(t), [t]);
  const form = useForm<TicketSummaryValues>({
    resolver: zodResolver(schema),
    defaultValues: { summary: preview.summary },
  });

  function onSubmit({ summary }: TicketSummaryValues) {
    create.mutate({ ...target, summary }, { onSuccess: onSent });
  }

  return (
    <Form {...form}>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
      >
        {create.isError && <FormAlert message={translateApiError(create.error, t)} />}
        <section aria-labelledby="ticket-question" className="flex flex-col gap-1">
          <h3 id="ticket-question" className="text-sm font-medium">
            {t("chat.ticket.question")}
          </h3>
          <blockquote className="border-l-2 pl-3 text-sm whitespace-pre-wrap">
            {preview.question}
          </blockquote>
        </section>
        <TextField
          control={form.control}
          name="summary"
          rows={5}
          label={t("chat.ticket.summary")}
          description={
            preview.summary_generated
              ? t("chat.ticket.summaryHint")
              : t("chat.ticket.summaryFallback")
          }
        />
        <p className="text-sm">
          {t("chat.ticket.requester", {
            name: preview.requester.name,
            email: preview.requester.email,
          })}
        </p>
        <p className="text-muted-foreground text-sm">
          {t("chat.ticket.messages", { count: preview.messages.length })}
        </p>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              {t("chat.ticket.cancel")}
            </Button>
          </DialogClose>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? t("chat.ticket.submitting") : t("chat.ticket.submit")}
          </Button>
        </DialogFooter>
      </form>
    </Form>
  );
}
