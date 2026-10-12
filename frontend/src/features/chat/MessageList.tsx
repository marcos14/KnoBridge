import { LifeBuoy } from "lucide-react";
import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { AssistantMessage } from "@/components/AssistantMessage";
import { Button } from "@/components/ui/button";
import type { PendingAnswer } from "@/lib/api/chatStream";
import type { Citation, Message } from "@/lib/api/conversations";

import { isAtEnd, questionBefore, visibleMessages } from "./chatForm";
import { FeedbackControls } from "./FeedbackControls";
import { TicketRequestState } from "./TicketRequestState";

interface MessageListProps {
  workspaceId: string;
  conversationId: string;
  /** Saved messages, in order. */
  messages: readonly Message[];
  /** The exchange being streamed, shown after the saved messages. */
  pending: PendingAnswer | null;
  onCitation: (citation: Citation) => void;
  /** Sends a question again; absent while an answer streams. */
  onResend?: (question: string) => void;
  /**
   * Opens "Abrir chamado" for an answer; absent when the assistant does not offer it (or while
   * an answer streams). Offered on the answers without a source.
   */
  onOpenTicket?: (messageId: string) => void;
}

function TicketSlot({
  workspaceId,
  message,
  onOpenTicket,
}: {
  workspaceId: string;
  message: Message;
  onOpenTicket?: (messageId: string) => void;
}) {
  const { t } = useTranslation();
  const request = message.ticket_request ?? null;
  if (request !== null) {
    return <TicketRequestState workspaceId={workspaceId} request={request} />;
  }
  if (onOpenTicket === undefined || message.status !== "no_source") {
    return null;
  }
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="w-fit"
      onClick={() => {
        onOpenTicket(message.id);
      }}
    >
      <LifeBuoy aria-hidden="true" />
      {t("chat.message.openTicket")}
    </Button>
  );
}

function UserMessage({ content }: { content: string }) {
  const { t } = useTranslation();
  return (
    <li className="bg-muted max-w-[85%] self-end rounded-lg px-3 py-2 text-sm whitespace-pre-wrap">
      <span className="sr-only">{t("chat.message.you")}: </span>
      {content}
    </li>
  );
}

/**
 * The thread. It follows the end while new text arrives, but only when the reader is already at
 * the end: scrolling up to read stops the following. The answer in progress sits in a polite live
 * region, so screen readers read it without interrupting.
 */
export function MessageList({
  workspaceId,
  conversationId,
  messages,
  pending,
  onCitation,
  onResend,
  onOpenTicket,
}: MessageListProps) {
  const { t } = useTranslation();
  const boxRef = useRef<HTMLDivElement | null>(null);
  const atEndRef = useRef(true);
  const visible = visibleMessages(messages, pending);

  useLayoutEffect(() => {
    const box = boxRef.current;
    if (box !== null && atEndRef.current) {
      box.scrollTop = box.scrollHeight;
    }
  }, [visible.length, pending?.text, pending?.citations.length, pending?.question]);

  function resendFor(message: Message) {
    const question = questionBefore(messages, message.id);
    if (onResend === undefined || question === null) {
      return undefined;
    }
    return () => {
      onResend(question);
    };
  }

  return (
    <div
      ref={boxRef}
      className="min-h-0 flex-1 overflow-y-auto pr-1"
      onScroll={(event) => {
        atEndRef.current = isAtEnd(event.currentTarget);
      }}
    >
      <ol aria-label={t("chat.thread.label")} className="flex flex-col gap-4 py-2">
        {visible.map((message) =>
          message.role === "user" ? (
            <UserMessage key={message.id} content={message.content} />
          ) : (
            <li key={message.id} className="max-w-[95%]">
              <span className="sr-only">{t("chat.message.assistant")}: </span>
              <AssistantMessage
                content={message.content}
                citations={message.citations}
                status={message.status}
                errorCode={message.error_code}
                onCitation={onCitation}
                onResend={resendFor(message)}
                ticket={
                  <TicketSlot
                    workspaceId={workspaceId}
                    message={message}
                    onOpenTicket={onOpenTicket}
                  />
                }
                feedback={
                  message.status === "completed" || message.status === "no_source" ? (
                    <FeedbackControls
                      workspaceId={workspaceId}
                      conversationId={conversationId}
                      message={message}
                    />
                  ) : undefined
                }
              />
            </li>
          ),
        )}
        {pending !== null && <UserMessage content={pending.question} />}
      </ol>
      <div aria-live="polite" className="max-w-[95%]">
        {pending !== null && (
          <AssistantMessage
            content={pending.text}
            citations={pending.citations}
            status="streaming"
            errorCode={null}
            onCitation={onCitation}
          />
        )}
      </div>
    </div>
  );
}
