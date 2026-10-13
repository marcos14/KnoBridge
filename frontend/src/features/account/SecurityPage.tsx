import { useTranslation } from "react-i18next";

import { AccountPage } from "./AccountPage";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { LogoutAllSection } from "./LogoutAllSection";
import { SessionsSection } from "./SessionsSection";

/** `/account/security`: change the password, manage the live sessions or end them all. */
export function SecurityPage() {
  const { t } = useTranslation();

  return (
    <AccountPage
      title={t("account.security.title")}
      description={t("account.security.description")}
    >
      <ChangePasswordForm />
      <SessionsSection />
      <LogoutAllSection />
    </AccountPage>
  );
}
