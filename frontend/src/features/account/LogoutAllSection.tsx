import { useTranslation } from "react-i18next";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { useLogoutAll } from "@/lib/api/auth";

import { AccountSection } from "./AccountSection";

/**
 * "Sair de todas as sessões": ends every session of the account, this one included, after a
 * confirmation. The tab is then logged out and the guards take the user to the login.
 */
export function LogoutAllSection() {
  const { t } = useTranslation();
  const logoutAll = useLogoutAll();

  return (
    <AccountSection
      title={t("account.security.logoutAll.title")}
      description={t("account.security.logoutAll.description")}
      actions={
        <ConfirmDialog
          trigger={
            <Button type="button" variant="outline" size="sm" disabled={logoutAll.isPending}>
              {t("account.security.logoutAll.submit")}
            </Button>
          }
          title={t("account.security.logoutAll.confirmTitle")}
          description={t("account.security.logoutAll.confirmDescription")}
          confirmLabel={t("account.security.logoutAll.submit")}
          onConfirm={() => {
            logoutAll.mutate();
          }}
        />
      }
    >
      {logoutAll.isError && <FormAlert message={translateApiError(logoutAll.error, t)} />}
    </AccountSection>
  );
}
