import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { TicketStatus } from "@/lib/citationLocation";

/**
 * Status seal of a ticket in pt-BR: solid for resolved and closed tickets (an answer was given),
 * outlined for open and pending ones (a problem still in progress).
 */
export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  const { t } = useTranslation();
  const settled = status === "resolved" || status === "closed";
  return <Badge variant={settled ? "default" : "outline"}>{t(`tickets.status.${status}`)}</Badge>;
}
