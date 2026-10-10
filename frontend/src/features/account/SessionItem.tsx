import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import type { Session } from "@/lib/api/account";
import { formatDateTime, formatRelativeTime } from "@/lib/intl";
import { summarizeUserAgent } from "@/lib/userAgent";

import { ConfirmAction } from "./ConfirmAction";
import { deviceLabel } from "./device";

interface SessionItemProps {
  session: Session;
  onRevoke: (session: Session) => void;
  disabled: boolean;
}

/** One live session: device, last use, start, network and the button that ends it. */
export function SessionItem({ session, onRevoke, disabled }: SessionItemProps) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  const locale = i18n.language;
  const device = deviceLabel(summarizeUserAgent(session.user_agent), t);
  const lastSeen = new Date(session.last_seen_at);

  return (
    <li className="flex flex-wrap items-center justify-between gap-4 py-4">
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{device}</span>
          {session.current && (
            <Badge variant="secondary">{t("account.security.sessions.current")}</Badge>
          )}
        </div>
        <p className="text-muted-foreground text-sm">
          <time dateTime={session.last_seen_at} title={formatDateTime(lastSeen, locale)}>
            {t("account.security.sessions.lastSeen", {
              when: formatRelativeTime(lastSeen, clock(), locale),
            })}
          </time>
        </p>
        <p className="text-muted-foreground text-sm">
          <time dateTime={session.created_at}>
            {t("account.security.sessions.createdAt", {
              date: formatDateTime(new Date(session.created_at), locale),
            })}
          </time>
          {session.ip_prefix !== null && (
            <> · {t("account.security.sessions.network", { ip: session.ip_prefix })}</>
          )}
        </p>
      </div>
      {session.current ? (
        <ConfirmAction
          label={t("account.security.sessions.revokeCurrent")}
          title={t("account.security.sessions.revokeCurrentTitle")}
          description={t("account.security.sessions.revokeCurrentDescription")}
          disabled={disabled}
          onConfirm={() => {
            onRevoke(session);
          }}
        />
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={t("account.security.sessions.revokeLabel", { device })}
          onClick={() => {
            onRevoke(session);
          }}
        >
          {t("account.security.sessions.revoke")}
        </Button>
      )}
    </li>
  );
}
