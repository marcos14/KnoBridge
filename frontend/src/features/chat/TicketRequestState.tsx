import { CheckCircle2, ExternalLink, LifeBuoy, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { translateApiErrorCode } from "@/i18n/apiErrors";
import { type TicketRequest, useTicketRequest } from "@/lib/api/ticketRequests";
import { webUrl } from "@/lib/citationLocation";

interface TicketRequestStateProps {
  workspaceId: string;
  request: TicketRequest;
}

/**
 * Where the ticket asked for an answer stands: being sent (read again until it ends), opened
 * (with the number and the link the destination gave) or failed (with the reason).
 */
export function TicketRequestState({ workspaceId, request }: TicketRequestStateProps) {
  const { t } = useTranslation();
  const current = useTicketRequest(workspaceId, request);

  if (current.status === "pending") {
    return (
      <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm">
        <LifeBuoy aria-hidden="true" className="size-4" />
        {t("chat.ticket.sending")}
      </p>
    );
  }
  if (current.status === "failed") {
    return (
      <p role="status" className="text-destructive flex items-center gap-2 text-sm">
        <XCircle aria-hidden="true" className="size-4" />
        {t("chat.ticket.failed", {
          reason: translateApiErrorCode(current.error_code ?? "unknown", t),
        })}
      </p>
    );
  }
  const link = webUrl(current.external_url);
  return (
    <div role="status" className="flex flex-wrap items-center gap-2 text-sm">
      <CheckCircle2 aria-hidden="true" className="size-4" />
      <span>
        {current.external_ticket_id === null
          ? t("chat.ticket.delivered")
          : t("chat.ticket.deliveredNumber", { number: current.external_ticket_id })}
      </span>
      {link !== null && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 underline underline-offset-4"
        >
          {t("chat.ticket.openLink")}
          <ExternalLink aria-hidden="true" className="size-3" />
        </a>
      )}
    </div>
  );
}
