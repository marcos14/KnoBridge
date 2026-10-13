import { ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";

import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/i18n/apiErrors";
import { useMe } from "@/lib/api/auth";
import { useLeaveWorkspaceAccess } from "@/lib/api/workspaceAccess";

/**
 * Strip shown on every page while this session holds a superadmin access to a workspace
 * (`superadmin_access` of `me`), with a link to it and "Sair". Leaving while inside that workspace,
 * without being a member, goes back to the administration's workspace list.
 */
export function SuperadminAccessBanner() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { workspaceId } = useParams();
  const { data: me } = useMe();
  const leave = useLeaveWorkspaceAccess();
  const access = me?.superadmin_access ?? null;

  if (access === null) {
    return null;
  }

  const name = access.workspace_name;
  const inside = workspaceId === access.workspace_id;

  function onLeave() {
    leave.mutate(undefined, {
      onSuccess: (after) => {
        const stillMember = after.workspaces.some((item) => item.id === workspaceId);
        if (inside && !stillMember) {
          void navigate("/admin/workspaces");
        }
      },
    });
  }

  return (
    <div
      role="region"
      aria-label={t("superadminAccess.label")}
      className="sticky top-0 z-20 flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-amber-300 bg-amber-100 px-4 py-2 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-50"
    >
      <ShieldAlert className="size-4 shrink-0" aria-hidden="true" />
      <p className="font-medium">{t("superadminAccess.banner", { name })}</p>
      <p className="hidden md:block">{t("superadminAccess.description")}</p>
      <div className="ml-auto flex items-center gap-2">
        {!inside && (
          <Link
            to={`/w/${access.workspace_id}`}
            className="underline"
            aria-label={t("superadminAccess.openLabel", { name })}
          >
            {t("superadminAccess.open")}
          </Link>
        )}
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={leave.isPending}
          aria-label={t("superadminAccess.leaveLabel", { name })}
          onClick={onLeave}
        >
          {leave.isPending ? t("superadminAccess.leaving") : t("superadminAccess.leave")}
        </Button>
      </div>
      {leave.isError && (
        <div className="basis-full">
          <FormAlert message={translateApiError(leave.error, t)} />
        </div>
      )}
    </div>
  );
}
