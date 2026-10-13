import { LifeBuoy } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { isApiErrorCode } from "@/lib/api/client";
import { useProducts } from "@/lib/api/products";
import type { ChatStream } from "@/lib/api/chatStream";
import { type Citation, useConversation } from "@/lib/api/conversations";
import { usePreviewTicketRequest } from "@/lib/api/ticketRequests";

import { ticketCandidate } from "./chatForm";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";
import { NoCollectionsHint } from "./NoCollectionsHint";
import { TicketRequestDialog } from "./TicketRequestDialog";

interface ConversationViewProps {
  workspaceId: string;
  conversationId: string;
  stream: ChatStream;
  onCitation: (citation: Citation) => void;
}

/** One conversation: its messages, the answer streaming now and the box for the next question. */
export function ConversationView({
  workspaceId,
  conversationId,
  stream,
  onCitation,
}: ConversationViewProps) {
  const { t } = useTranslation();
  const conversation = useConversation(workspaceId, conversationId);
  const assistants = useProducts(workspaceId);
  const [ticketFor, setTicketFor] = useState<string | null>(null);
  const preview = usePreviewTicketRequest(workspaceId);
  const streaming = stream.pending !== null;
  const pending = stream.pending?.conversationId === conversationId ? stream.pending : null;
  const send = (content: string) => stream.send(conversationId, content);
  const failure =
    stream.failure?.conversationId === conversationId
      ? translateApiError(stream.failure.error, t)
      : null;

  if (conversation.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("chat.conversation.loading")}
      </p>
    );
  }
  if (conversation.isError) {
    if (isApiErrorCode(conversation.error, "not_found")) {
      return (
        <div className="flex flex-col items-start gap-2">
          <h2 className="text-lg font-semibold">{t("chat.conversation.notFound")}</h2>
          <Link to={`/w/${workspaceId}/chat`} className="text-sm underline underline-offset-4">
            {t("chat.list.new")}
          </Link>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-start gap-2">
        <p role="alert" className="text-sm">
          {t("chat.conversation.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void conversation.refetch();
          }}
        >
          {t("chat.retry")}
        </Button>
      </div>
    );
  }

  const detail = conversation.data;
  const assistant = assistants.data?.find((item) => item.id === detail.product_id);
  // The detail says whether the assistant offers tickets; after each answer it is reloaded, so it
  // carries the same `ticket_requests_enabled` as the stream's `done` event.
  const openTicket =
    detail.ticket_requests_enabled && !streaming
      ? (messageId: string) => {
          setTicketFor(messageId);
          preview.reset();
          preview.mutate({ conversationId, messageId });
        }
      : undefined;
  const candidate = openTicket === undefined ? null : ticketCandidate(detail.messages.items);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <header className="flex flex-wrap items-start justify-between gap-2 border-b pb-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="truncate text-lg font-semibold">
            {detail.title ?? t("chat.list.untitled")}
          </h2>
          {assistant !== undefined && (
            <p className="text-muted-foreground text-xs">
              {t("chat.conversation.assistant", { name: assistant.name })}
            </p>
          )}
        </div>
        {openTicket !== undefined && candidate !== null && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              openTicket(candidate.id);
            }}
          >
            <LifeBuoy aria-hidden="true" />
            {t("chat.conversation.openTicket")}
          </Button>
        )}
      </header>
      <TicketRequestDialog
        workspaceId={workspaceId}
        conversationId={conversationId}
        messageId={ticketFor}
        preview={preview}
        onClose={() => {
          setTicketFor(null);
        }}
      />
      <MessageList
        workspaceId={workspaceId}
        conversationId={conversationId}
        messages={detail.messages.items}
        pending={pending}
        onCitation={onCitation}
        onOpenTicket={openTicket}
        onResend={
          streaming
            ? undefined
            : (question) => {
                void send(question);
              }
        }
      />
      {failure !== null && <FormAlert key={failure} message={failure} />}
      <NoCollectionsHint assistant={assistant} />
      <Composer onSend={send} streaming={streaming} onStop={stream.stop} />
    </div>
  );
}
