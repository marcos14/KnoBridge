import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { useLogout, useMe } from "@/lib/api/auth";
import { isApiErrorCode } from "@/lib/api/client";
import {
  type AcceptInvitationInput,
  type InvitationPreview,
  useAcceptInvitation,
  useInvitationPreview,
} from "@/lib/api/invites";
import { readStoredItem, removeStoredItem, writeStoredItem } from "@/lib/storage";

import { AuthCard } from "./AuthCard";
import { FormAlert } from "./FormAlert";
import { GuardError, GuardLoading } from "./GuardStatus";
import { invitationStep } from "./invitationStep";
import { InvitationSignupForm } from "./InvitationSignupForm";
import { ACCEPT_INVITATION_PATH, LOGIN_PATH, loginPath } from "./redirect";
import { useUrlToken } from "./useUrlToken";

/**
 * Where the token waits while the invitee logs in: this tab's `sessionStorage`, so the login can
 * bring them back to a plain `/accept-invitation` without the token travelling in `?next=`.
 */
export const INVITATION_TOKEN_KEY = "knobridge.pendingInvitation";

/** Login that comes back to this screen afterwards. */
const LOGIN_TO_ACCEPT = loginPath({ pathname: ACCEPT_INVITATION_PATH, search: "", hash: "" });

/** Token of the link just opened, or the one kept in the tab before going to the login. */
function useInvitationToken(): string | undefined {
  const urlToken = useUrlToken();
  const [storedToken] = useState(() => readStoredItem(INVITATION_TOKEN_KEY, "session"));

  useEffect(() => {
    if (urlToken !== undefined) {
      writeStoredItem(INVITATION_TOKEN_KEY, urlToken, "session");
    }
  }, [urlToken]);

  return urlToken ?? storedToken;
}

function InvitationSummary({ preview }: { preview: InvitationPreview }) {
  const { t } = useTranslation();
  const values = {
    workspace: preview.workspace_name,
    role: t(`roles.${preview.role}`),
    inviter: preview.inviter_name,
  };

  return (
    <div className="flex flex-col gap-1">
      <p>
        {preview.inviter_name === null
          ? t("auth.acceptInvitation.invited", values)
          : t("auth.acceptInvitation.invitedBy", values)}
      </p>
      <p className="text-muted-foreground text-sm">
        {t("auth.acceptInvitation.invitedEmail", { email: preview.email })}
      </p>
    </div>
  );
}

/**
 * `/accept-invitation?token=`: shows the invitation and joins the workspace, creating the account
 * or using the one already logged in. Afterwards goes to the workspace.
 */
export function AcceptInvitationPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const token = useInvitationToken();
  const preview = useInvitationPreview(token);
  const me = useMe();
  const accept = useAcceptInvitation();
  const logout = useLogout();
  const title = t("auth.acceptInvitation.title");

  const invalid =
    token === undefined ||
    isApiErrorCode(preview.error, "invalid_token") ||
    isApiErrorCode(accept.error, "invalid_token");

  useEffect(() => {
    if (invalid) {
      removeStoredItem(INVITATION_TOKEN_KEY, "session");
    }
  }, [invalid]);

  if (invalid) {
    return (
      <AuthCard title={title}>
        <p role="alert">{t("auth.acceptInvitation.invalid")}</p>
        <Link to={LOGIN_PATH} className="text-sm underline underline-offset-4">
          {t("auth.backToLogin")}
        </Link>
      </AuthCard>
    );
  }

  if (preview.isError || me.isError) {
    return (
      <AuthCard title={title}>
        <GuardError
          onRetry={() => {
            void preview.refetch();
            void me.refetch();
          }}
        />
      </AuthCard>
    );
  }

  if (preview.isPending || me.isPending) {
    return (
      <AuthCard title={title}>
        <GuardLoading />
      </AuthCard>
    );
  }

  const { workspace_id: workspaceId } = preview.data;

  function acceptWith(body: AcceptInvitationInput) {
    accept.mutate(body, {
      onSuccess: () => {
        removeStoredItem(INVITATION_TOKEN_KEY, "session");
        void navigate(`/w/${workspaceId}`, { replace: true });
      },
      onError: (error) => {
        // The address got an account since the preview: log in with it and come back.
        if (isApiErrorCode(error, "login_required")) {
          void navigate(LOGIN_TO_ACCEPT, { replace: true });
        }
      },
    });
  }

  const step = isApiErrorCode(accept.error, "invitation_email_mismatch")
    ? "mismatch"
    : invitationStep(preview.data, me.data);
  const showError = accept.isError && step !== "mismatch";

  return (
    <AuthCard title={title}>
      <InvitationSummary preview={preview.data} />
      {showError && <FormAlert message={translateApiError(accept.error, t)} />}
      {step === "signup" && (
        <InvitationSignupForm
          pending={accept.isPending}
          onSubmit={(values) => {
            acceptWith({ token, ...values });
          }}
        />
      )}
      {step === "login" && (
        <>
          <p>{t("auth.acceptInvitation.loginToAccept", { email: preview.data.email })}</p>
          <Button asChild>
            <Link to={LOGIN_TO_ACCEPT}>{t("auth.acceptInvitation.login")}</Link>
          </Button>
        </>
      )}
      {step === "accept" && (
        <>
          <p>{t("auth.acceptInvitation.acceptAs", { email: preview.data.email })}</p>
          <Button
            type="button"
            disabled={accept.isPending}
            onClick={() => {
              acceptWith({ token });
            }}
          >
            {accept.isPending ? t("auth.submitting") : t("auth.acceptInvitation.accept")}
          </Button>
        </>
      )}
      {step === "mismatch" && (
        <>
          <p role="alert">{t("auth.acceptInvitation.mismatch", { invited: preview.data.email })}</p>
          <Button
            type="button"
            variant="outline"
            disabled={logout.isPending}
            onClick={() => {
              logout.mutate(undefined, {
                onSuccess: () => {
                  accept.reset();
                },
              });
            }}
          >
            {t("auth.acceptInvitation.logout")}
          </Button>
        </>
      )}
    </AuthCard>
  );
}
