import { useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { PendingAnswer } from "@/lib/api/chatStream";
import type { Citation, Message } from "@/lib/api/conversations";

import { AssistantMessage } from "./AssistantMessage";
import { isAtEnd, questionBefore } from "./chatForm";
import { FeedbackControls } from "./FeedbackControls";

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
}: MessageListProps) {
  const { t } = useTranslation();
  const boxRef = useRef<HTMLDivElement | null>(null);
  const atEndRef = useRef(true);
  // Saved messages already being shown by the pending exchange (between reload and its end).
  const visible = messages.filter(
    (message) => message.id !== pending?.messageId && message.id !== pending?.userMessageId,
  );

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
