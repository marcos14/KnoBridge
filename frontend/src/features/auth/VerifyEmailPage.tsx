import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { isApiErrorCode } from "@/lib/api/client";
import { useVerifyEmail } from "@/lib/api/recovery";

import { AuthCard } from "./AuthCard";
import { FormAlert } from "./FormAlert";
import { useUrlToken } from "./useUrlToken";

/** `/verify-email?token=`: confirms the address as soon as the e-mailed link is opened. */
export function VerifyEmailPage() {
  const { t } = useTranslation();
  const token = useUrlToken();
  const verify = useVerifyEmail();
  const { mutate } = verify;
  // The token is single use: a second request (StrictMode runs effects twice) would get a 400.
  const sent = useRef(false);

  useEffect(() => {
    if (token !== undefined && !sent.current) {
      sent.current = true;
      mutate({ token });
    }
  }, [token, mutate]);

  const title = t("auth.verifyEmail.title");

  if (token === undefined || isApiErrorCode(verify.error, "invalid_token")) {
    return (
      <AuthCard title={title}>
        <p role="alert">{t("auth.verifyEmail.invalid")}</p>
        <Link to="/" className="text-sm underline underline-offset-4">
          {t("auth.verifyEmail.goToPanel")}
        </Link>
      </AuthCard>
    );
  }

  if (verify.isError) {
    return (
      <AuthCard title={title}>
        <FormAlert message={translateApiError(verify.error, t)} />
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            mutate({ token });
          }}
        >
          {t("auth.verifyEmail.retry")}
        </Button>
      </AuthCard>
    );
  }

  if (verify.isSuccess) {
    return (
      <AuthCard title={title}>
        <p role="status">{t("auth.verifyEmail.done")}</p>
        <Button asChild>
          <Link to="/">{t("auth.verifyEmail.goToPanel")}</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={title}>
      <p aria-busy="true">{t("auth.verifyEmail.verifying")}</p>
    </AuthCard>
  );
}
