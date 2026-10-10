import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { useRevokeOtherSessions, useRevokeSession, useSessions } from "@/lib/api/account";

import { AccountSection } from "./AccountSection";
import { ConfirmAction } from "./ConfirmAction";
import { SessionItem } from "./SessionItem";

/** Live sessions of the account: end one, or every one but this. */
export function SessionsSection() {
  const { t } = useTranslation();
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();
  const busy = revoke.isPending || revokeOthers.isPending;
  const othersCount = sessions.data?.filter((session) => !session.current).length ?? 0;

  return (
    <AccountSection
      title={t("account.security.sessions.title")}
      description={t("account.security.sessions.description")}
      actions={
        sessions.isSuccess && (
          <ConfirmAction
            label={t("account.security.sessions.revokeOthers")}
            title={t("account.security.sessions.revokeOthersTitle")}
            description={t("account.security.sessions.revokeOthersDescription")}
            disabled={busy || othersCount === 0}
            onConfirm={() => {
              revoke.reset();
              revokeOthers.mutate();
            }}
          />
        )
      }
    >
      {sessions.isPending && (
        <p role="status" className="text-sm">
          {t("account.security.sessions.loading")}
        </p>
      )}
      {sessions.isError && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert" className="text-sm">
            {t("account.security.sessions.loadFailed")}
          </p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void sessions.refetch();
            }}
          >
            {t("account.security.sessions.retry")}
          </Button>
        </div>
      )}
      {revoke.isError && <FormAlert message={translateApiError(revoke.error, t)} />}
      {revokeOthers.isError && <FormAlert message={translateApiError(revokeOthers.error, t)} />}
      {revokeOthers.isSuccess && (
        <p role="status" className="text-sm">
          {t("account.security.sessions.revokedOthers")}
        </p>
      )}
      {sessions.isSuccess && (
        <>
          {othersCount === 0 && !revokeOthers.isSuccess && (
            <p className="text-muted-foreground text-sm">
              {t("account.security.sessions.onlyCurrent")}
            </p>
          )}
          <ul className="divide-y">
            {sessions.data.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                disabled={busy}
                onRevoke={(target) => {
                  revokeOthers.reset();
                  revoke.mutate(target);
                }}
              />
            ))}
          </ul>
        </>
      )}
    </AccountSection>
  );
}
