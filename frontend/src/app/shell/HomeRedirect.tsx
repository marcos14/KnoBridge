import { useTranslation } from "react-i18next";
import { Link, Navigate } from "react-router";

import { useMe } from "@/lib/api/auth";
import { pickWorkspace, readLastWorkspaceId } from "@/lib/lastWorkspace";

/** `/`: opens the last used workspace (or the first one); without any, explains what to do. */
export function HomeRedirect() {
  const { data: me } = useMe();
  const workspace = pickWorkspace(me?.workspaces ?? [], readLastWorkspaceId());

  if (workspace) {
    return <Navigate to={`/w/${workspace.id}`} replace />;
  }
  return <NoWorkspace isSuperadmin={me?.is_superadmin === true} />;
}

function NoWorkspace({ isSuperadmin }: { isSuperadmin: boolean }) {
  const { t } = useTranslation();

  return (
    <section className="flex max-w-prose flex-col gap-2">
      <h1 className="text-xl font-semibold">{t("noWorkspace.title")}</h1>
      <p>{t("noWorkspace.description")}</p>
      {isSuperadmin && (
        <Link to="/admin/workspaces" className="underline">
          {t("noWorkspace.adminShortcut")}
        </Link>
      )}
    </section>
  );
}
