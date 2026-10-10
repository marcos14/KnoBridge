import { useTranslation } from "react-i18next";
import { NavLink, useMatch } from "react-router";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { useMe } from "@/lib/api/auth";

import { adminNavItems, workspaceNavItems, type NavItem } from "./navItems";
import { useActiveWorkspace } from "./useActiveWorkspace";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

interface NavMenuLinkProps {
  item: NavItem<string>;
  label: string;
}

function NavMenuLink({ item, label }: NavMenuLinkProps) {
  const isActive = useMatch({ path: item.to, end: item.end }) !== null;
  const { isMobile, setOpenMobile } = useSidebar();
  const Icon = item.icon;

  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={isActive} tooltip={label}>
        <NavLink
          to={item.to}
          end={item.end}
          onClick={() => {
            // On phones the menu is a sheet over the page: close it once a destination is chosen.
            if (isMobile) {
              setOpenMobile(false);
            }
          }}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </NavLink>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

/** Collapsible side menu: workspace switcher, the workspace areas the role allows and the admin. */
export function AppSidebar() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const workspace = useActiveWorkspace();

  return (
    <Sidebar
      collapsible="icon"
      mobileTitle={t("shell.sidebarTitle")}
      mobileDescription={t("shell.sidebarDescription")}
    >
      <SidebarHeader>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <nav aria-label={t("nav.label")}>
          {workspace && (
            <SidebarGroup>
              <SidebarGroupLabel>{t("nav.workspaceGroup")}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {workspaceNavItems(workspace.id, workspace.role).map((item) => (
                    <NavMenuLink key={item.key} item={item} label={t(`nav.items.${item.key}`)} />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
          {me?.is_superadmin === true && (
            <SidebarGroup>
              <SidebarGroupLabel>{t("nav.adminGroup")}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {adminNavItems().map((item) => (
                    <NavMenuLink
                      key={item.key}
                      item={item}
                      label={t(`nav.adminItems.${item.key}`)}
                    />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
        </nav>
      </SidebarContent>
    </Sidebar>
  );
}
