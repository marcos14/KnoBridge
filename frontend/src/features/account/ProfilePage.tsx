import { useTranslation } from "react-i18next";

import { useMe } from "@/lib/api/auth";

import { AccountPage } from "./AccountPage";
import { EmailSection } from "./EmailSection";
import { ProfileForm } from "./ProfileForm";

/** `/account/profile`: e-mail and its verification, name, language and theme. */
export function ProfilePage() {
  const { t } = useTranslation();
  const { data: me } = useMe();

  // The route sits under RequireAuth, which renders it only once `me` is loaded.
  if (!me) {
    return null;
  }

  return (
    <AccountPage title={t("account.profile.title")} description={t("account.profile.description")}>
      <EmailSection user={me.user} />
      <ProfileForm user={me.user} />
    </AccountPage>
  );
}
