import type { TFunction } from "i18next";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router";

import { AssistantMessage } from "@/components/AssistantMessage";
import { CitationSheet } from "@/components/CitationSheet";
import { Button } from "@/components/ui/button";
import { isApiErrorCode } from "@/lib/api/client";
import type { Citation } from "@/lib/api/conversations";
import {
  useWorkspaceConversation,
  type WorkspaceConversationDetail,
  type WorkspaceMessage,
} from "@/lib/api/workspaceConversations";
import { stepQueries } from "@/lib/answerSteps";
import { formatDateTime } from "@/lib/intl";
import { levelLabel } from "@/lib/responseLevels";

import { conversationOwner } from "./conversationOwner";
import { FeedbackList } from "./FeedbackList";

interface WorkspaceConversationViewProps {
  workspaceId: string;
  conversationId: string;
}

/** "Ana (ana@…) em ERP, nível Suporte", "MCP · ERP em …" or "Widget · Site · Visitante … em …". */
function whoText(conversation: WorkspaceConversationDetail, t: TFunction): string {
  const product = conversation.product_name;
  const level = levelLabel(conversation.level, t);
  if (conversation.channel === "panel") {
    return t("conversations.detail.who", {
      user: conversation.user_name,
      email: conversation.user_email,
      product,
      level,
    });
  }
  const owner = conversationOwner(conversation, t);
  return conversation.channel === "widget"
    ? t("conversations.detail.whoWidget", {
        owner: owner.name,
        visitor: owner.detail,
        product,
        level,
      })
    : t("conversations.detail.whoApi", { owner: owner.name, product, level });
}

/**
 * Any conversation of the workspace (a member's, an API or MCP key's or a widget visitor's), read
 * only: the questions, the answers rendered as in the chat (safe
 * Markdown, sources, status) and the ratings each answer received. The way back keeps the filters
 * of the list, which travel in the query string.
 */
export function WorkspaceConversationView({
  workspaceId,
  conversationId,
}: WorkspaceConversationViewProps) {
  const { t } = useTranslation();
  const { search } = useLocation();
  const conversation = useWorkspaceConversation(workspaceId, conversationId);
  const [citation, setCitation] = useState<Citation | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <Link
        to={{ pathname: `/w/${workspaceId}/conversations`, search }}
        className="inline-flex w-fit items-center gap-1 text-sm underline-offset-4 hover:underline"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        {t("conversations.detail.back")}
      </Link>
      {conversation.isPending ? (
        <p role="status" className="text-sm">
          {t("conversations.detail.loading")}
        </p>
      ) : conversation.isError ? (
        isApiErrorCode(conversation.error, "not_found") ? (
          <h2 className="text-lg font-semibold">{t("conversations.detail.notFound")}</h2>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-sm">
              {t("conversations.detail.loadFailed")}
            </p>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void conversation.refetch();
              }}
            >
              {t("conversations.retry")}
            </Button>
          </div>
        )
      ) : (
        <ConversationThread
          title={conversation.data.title}
          who={whoText(conversation.data, t)}
          userName={conversationOwner(conversation.data, t).asker}
          createdAt={conversation.data.created_at}
          messages={conversation.data.messages.items}
          onCitation={setCitation}
        />
      )}
      <CitationSheet
        citation={citation}
        onClose={() => {
          setCitation(null);
        }}
      />
    </div>
  );
}

interface ConversationThreadProps {
  title: string | null;
  who: string;
  userName: string;
  createdAt: string;
  messages: readonly WorkspaceMessage[];
  onCitation: (citation: Citation) => void;
}

function ConversationThread({
  title,
  who,
  userName,
  createdAt,
  messages,
  onCitation,
}: ConversationThreadProps) {
  const { t, i18n } = useTranslation();

  return (
    <article className="flex flex-col gap-4">
      <header className="flex flex-col gap-1 border-b pb-3">
        <h2 className="text-lg font-semibold">{title ?? t("conversations.untitled")}</h2>
        <p className="text-sm">{who}</p>
        <p className="text-muted-foreground text-xs">
          {t("conversations.detail.startedAt", {
            when: formatDateTime(new Date(createdAt), i18n.language),
          })}{" "}
          · {t("conversations.detail.readOnly")}
        </p>
      </header>
      {messages.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("conversations.detail.empty")}</p>
      ) : (
        <ol aria-label={t("conversations.detail.threadLabel")} className="flex flex-col gap-4">
          {messages.map((message) =>
            message.role === "user" ? (
              <li
                key={message.id}
                className="bg-muted max-w-[85%] self-end rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
              >
                <span className="sr-only">
                  {t("conversations.detail.question", { name: userName })}:{" "}
                </span>
                {message.content}
              </li>
            ) : (
              <li key={message.id} className="flex max-w-[95%] flex-col gap-2">
                <span className="sr-only">{t("conversations.detail.answer")}: </span>
                <AssistantMessage
                  readOnly
                  content={message.content}
                  citations={message.citations}
                  status={message.status}
                  errorCode={message.error_code}
                  steps={message.steps}
                  stepQueries={stepQueries(message.retrieval)}
                  onCitation={onCitation}
                  feedback={<FeedbackList feedback={message.feedback} />}
                />
                <MessageMeta message={message} />
              </li>
            ),
          )}
        </ol>
      )}
    </article>
  );
}

/** Model and latency of an answer, when the server recorded them. */
function MessageMeta({ message }: { message: WorkspaceMessage }) {
  const { t } = useTranslation();
  const parts = [
    message.model === null ? null : t("conversations.detail.model", { model: message.model }),
    message.latency_ms === null
      ? null
      : t("conversations.detail.latency", { latency: message.latency_ms }),
  ].filter((part) => part !== null);

  if (parts.length === 0) {
    return null;
  }
  return <p className="text-muted-foreground text-xs">{parts.join(" · ")}</p>;
}
