import { ChevronsUpDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useMe } from "@/lib/api/auth";

import { useActiveWorkspace } from "./useActiveWorkspace";

/** Lists the user's workspaces (from `me`); choosing one opens its home. */
export function WorkspaceSwitcher() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const active = useActiveWorkspace();
  const workspaces = me?.workspaces ?? [];

  if (workspaces.length === 0) {
    return null;
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" aria-label={t("workspaceSwitcher.label")}>
              <span className="truncate font-medium">
                {active?.name ?? t("workspaceSwitcher.placeholder")}
              </span>
              <ChevronsUpDown className="ml-auto" aria-hidden="true" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-56">
            <DropdownMenuLabel>{t("workspaceSwitcher.listLabel")}</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={active?.id ?? ""}
              onValueChange={(workspaceId) => {
                void navigate(`/w/${workspaceId}`);
              }}
            >
              {workspaces.map((workspace) => (
                <DropdownMenuRadioItem key={workspace.id} value={workspace.id}>
                  {workspace.name}
                  {workspace.access === "superadmin" && (
                    <span className="text-muted-foreground ml-auto text-xs">
                      {t("workspaceSwitcher.superadmin")}
                    </span>
                  )}
                  {workspace.status === "suspended" && (
                    <span className="text-muted-foreground ml-auto text-xs">
                      {t("workspaceSwitcher.suspended")}
                    </span>
                  )}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
