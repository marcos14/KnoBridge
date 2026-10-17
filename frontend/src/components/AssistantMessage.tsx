import { AlertTriangle, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { translateApiErrorCode } from "@/i18n/apiErrors";
import type { Citation, MessageStatus } from "@/lib/api/conversations";
import { citationLocation, citationSource } from "@/lib/citationLocation";

import { ChatMarkdown } from "./ChatMarkdown";

interface AssistantMessageProps {
  content: string;
  citations: readonly Citation[];
  status: MessageStatus;
  errorCode: string | null;
  onCitation: (citation: Citation) => void;
  /** Sends the question again (failed or interrupted answers); absent when it cannot be resent. */
  onResend?: () => void;
  /** Rating controls (chat) or the ratings received (conversations), for finished answers. */
  feedback?: ReactNode;
  /** "Abrir chamado" or the state of the ticket asked for this answer (chat only). */
  ticket?: ReactNode;
  /** Someone else's answer seen by an administrator: no ticket offer, the status said in words. */
  readOnly?: boolean;
  /**
   * While streaming, the last search the model started (`step` event): "Buscando: <query>"
   * instead of "respondendo" until the first text arrives.
   */
  searching?: { query: string | null } | null;
  /** Searches made by the finished answer (`steps`); absent, `null` or `0`, nothing is shown. */
  steps?: number | null;
  /** The queries the model wrote in those searches (`retrieval`), shown when the count opens. */
  stepQueries?: readonly string[];
}

/** "N buscas" of an answer and, when the model searched again, the queries it wrote. */
function StepsSummary({ steps, queries }: { steps: number; queries: readonly string[] }) {
  const { t } = useTranslation();
  const label = t("chat.message.steps", { count: steps });
  if (queries.length === 0) {
    return <p className="text-muted-foreground text-xs">{label}</p>;
  }
  return (
    <details className="text-muted-foreground text-xs">
      <summary className="w-fit cursor-pointer">{label}</summary>
      <ol aria-label={t("chat.message.stepsQueries")} className="mt-1 list-decimal pl-5">
        <li>{t("chat.message.stepsQuestion")}</li>
        {queries.map((query, index) => (
          <li key={index}>{query}</li>
        ))}
      </ol>
    </details>
  );
}

/**
 * One answer of the assistant: Markdown with its sources, what happened to it and its actions.
 * Shared by the chat and the read-only view of the conversations screen.
 */
export function AssistantMessage({
  content,
  citations,
  status,
  errorCode,
  onCitation,
  onResend,
  feedback,
  ticket,
  readOnly = false,
  searching = null,
  steps = null,
  stepQueries = [],
}: AssistantMessageProps) {
  const { t } = useTranslation();
  const problem =
    status === "failed"
      ? translateApiErrorCode(errorCode ?? "chat_failed", t)
      : status === "interrupted"
        ? t("chat.message.interrupted")
        : null;

  return (
    <div className="flex flex-col gap-3">
      {content !== "" && (
        <ChatMarkdown content={content} citations={citations} onCitation={onCitation} />
      )}
      {status === "streaming" && content === "" && (
        <p className="text-muted-foreground text-sm">
          {searching === null
            ? t("chat.message.thinking")
            : searching.query === null
              ? t("chat.message.searching")
              : t("chat.message.searchingFor", { query: searching.query })}
        </p>
      )}
      {citations.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-muted-foreground text-xs font-medium">{t("chat.citations.title")}</p>
          <ul className="flex flex-wrap gap-2">
            {citations.map((citation) => {
              const source = citationSource(citation);
              const location =
                source.type === "ticket" && source.number !== null
                  ? t("chat.citations.ticketNumber", { number: source.number })
                  : source.type === "card" && source.number !== null
                    ? t("chat.citations.cardNumber", { number: source.number })
                    : citationLocation(citation);
              const seal =
                source.type === "knowledge" && source.confidence !== null
                  ? t(`chat.citations.seals.${source.confidence}`)
                  : source.type === "ticket" && source.status !== null
                    ? t(`tickets.status.${source.status}`)
                    : source.type === "card" && source.status !== null
                      ? t(`cards.status.${source.status}`)
                      : null;
              return (
                <li key={citation.index}>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-auto max-w-64 flex-col items-start gap-0 py-1 text-left whitespace-normal"
                    onClick={() => {
                      onCitation(citation);
                    }}
                  >
                    <span>
                      [{citation.index}] {citation.title}
                    </span>
                    {/* Keeps title and location apart in the accessible name; the flex column
                        drops it visually. */}
                    {location !== null && " "}
                    {location !== null && (
                      <span className="text-muted-foreground font-mono text-xs break-all">
                        {location}
                      </span>
                    )}
                    {seal !== null && " "}
                    {seal !== null && <span className="text-muted-foreground text-xs">{seal}</span>}
                  </Button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {steps !== null && steps > 0 && <StepsSummary steps={steps} queries={stepQueries} />}
      {status === "no_source" && readOnly && (
        <p className="text-muted-foreground text-xs">{t("chat.message.noSource")}</p>
      )}
      {ticket}
      {problem !== null && (
        <div className="border-destructive/40 text-destructive flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <AlertTriangle aria-hidden="true" className="size-4" />
          <span>{problem}</span>
          {onResend !== undefined && (
            <Button type="button" variant="outline" size="sm" onClick={onResend}>
              <RotateCcw aria-hidden="true" />
              {t("chat.message.resend")}
            </Button>
          )}
        </div>
      )}
      {feedback}
    </div>
  );
}
