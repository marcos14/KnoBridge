import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useClock } from "@/hooks/use-clock";
import { translateApiError } from "@/i18n/apiErrors";
import { useResendVerification } from "@/lib/api/account";
import type { Me } from "@/lib/api/auth";
import { isApiErrorCode, retryAfterSeconds } from "@/lib/api/client";
import { formatRelativeTime } from "@/lib/intl";

import { AccountSection } from "./AccountSection";

interface EmailSectionProps {
  user: Me["user"];
}

/** Message for a refused resend: how long to wait when the API says so, else the generic one. */
function resendErrorMessage(error: unknown, now: Date, locale: string, t: TFunction): string {
  const seconds = retryAfterSeconds(error);
  if (seconds === undefined) {
    return translateApiError(error, t);
  }
  const when = formatRelativeTime(new Date(now.getTime() + seconds * 1000), now, locale);
  return t("account.profile.email.tooMany", { when });
}

/** The login address (read only), whether it is verified and, if not, a new verification link. */
export function EmailSection({ user }: EmailSectionProps) {
  const { t, i18n } = useTranslation();
  const clock = useClock();
  const resend = useResendVerification();
  const verified = user.email_verified_at !== null;
  const alreadyVerified = isApiErrorCode(resend.error, "email_already_verified");

  return (
    <AccountSection
      title={t("account.profile.email.title")}
      description={t("account.profile.email.readOnly")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium break-all">{user.email}</span>
        <Badge variant={verified ? "secondary" : "outline"}>
          {verified ? t("account.profile.email.verified") : t("account.profile.email.unverified")}
        </Badge>
      </div>
      {resend.isSuccess && (
        <p role="status" className="text-sm">
          {t("account.profile.email.resent", { email: user.email })}
        </p>
      )}
      {alreadyVerified && (
        <p role="status" className="text-sm">
          {t("account.profile.email.alreadyVerified")}
        </p>
      )}
      {resend.isError && !alreadyVerified && (
        <FormAlert message={resendErrorMessage(resend.error, clock(), i18n.language, t)} />
      )}
      {!verified && (
        <div className="flex flex-col items-start gap-3">
          <p className="text-muted-foreground text-sm">
            {t("account.profile.email.unverifiedHint")}
          </p>
          <Button
            type="button"
            variant="outline"
            disabled={resend.isPending}
            onClick={() => {
              resend.mutate();
            }}
          >
            {resend.isPending ? t("auth.submitting") : t("account.profile.email.resend")}
          </Button>
        </div>
      )}
    </AccountSection>
  );
}
