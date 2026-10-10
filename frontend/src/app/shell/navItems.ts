import {
  Bot,
  Building2,
  Cable,
  Cpu,
  Database,
  House,
  Library,
  MessageSquare,
  MessagesSquare,
  ScrollText,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

import { hasRole } from "@/lib/roles";
import type { Role } from "@/lib/api/auth";

export type WorkspaceArea =
  | "home"
  | "chat"
  | "conversations"
  | "assistants"
  | "providers"
  | "sources"
  | "pipelines"
  | "collections"
  | "channels"
  | "members"
  | "settings"
  | "audit";

export type AdminArea = "workspaces" | "users" | "audit";

interface AreaDefinition<Key extends string> {
  key: Key;
  /** Path below the area root (`/w/:workspaceId` or `/admin`); "" is the root itself. */
  path: string;
  icon: LucideIcon;
}

interface WorkspaceAreaDefinition extends AreaDefinition<WorkspaceArea> {
  /** Least privileged role that sees the menu item and may open the route. */
  minRole: Role;
}

/**
 * Areas of a workspace, in menu order, with the role each one requires. The router reads the same
 * table, so a menu item and its route guard can never disagree.
 */
export const WORKSPACE_AREAS: readonly WorkspaceAreaDefinition[] = [
  { key: "home", path: "", minRole: "viewer", icon: House },
  { key: "chat", path: "chat", minRole: "viewer", icon: MessageSquare },
  { key: "conversations", path: "conversations", minRole: "admin", icon: MessagesSquare },
  { key: "assistants", path: "assistants", minRole: "editor", icon: Bot },
  { key: "providers", path: "providers", minRole: "editor", icon: Cpu },
  { key: "sources", path: "sources", minRole: "viewer", icon: Database },
  { key: "pipelines", path: "pipelines", minRole: "viewer", icon: Workflow },
  { key: "collections", path: "collections", minRole: "viewer", icon: Library },
  { key: "channels", path: "channels", minRole: "viewer", icon: Cable },
  { key: "members", path: "members", minRole: "viewer", icon: Users },
  { key: "settings", path: "settings", minRole: "admin", icon: Settings },
  { key: "audit", path: "audit", minRole: "admin", icon: ScrollText },
];

export const ADMIN_AREAS: readonly AreaDefinition<AdminArea>[] = [
  { key: "workspaces", path: "workspaces", icon: Building2 },
  { key: "users", path: "users", icon: UserCog },
  { key: "audit", path: "audit", icon: ShieldCheck },
];

export interface NavItem<Key extends string> {
  key: Key;
  to: string;
  /** Active only on this exact path (the workspace home), not on its children. */
  end: boolean;
  icon: LucideIcon;
}

/** Role required by a workspace area; also used by the router to guard its route. */
export function areaMinRole(area: WorkspaceArea): Role {
  const definition = WORKSPACE_AREAS.find(({ key }) => key === area);
  if (definition === undefined) {
    throw new Error(`Unknown workspace area: ${area}`);
  }
  return definition.minRole;
}

function joinPath(root: string, path: string): string {
  return path === "" ? root : `${root}/${path}`;
}

/** Menu items of workspace `workspaceId` visible to `role`. */
export function workspaceNavItems(workspaceId: string, role: Role): NavItem<WorkspaceArea>[] {
  const root = `/w/${workspaceId}`;
  return WORKSPACE_AREAS.filter(({ minRole }) => hasRole(role, minRole)).map(
    ({ key, path, icon }) => ({ key, to: joinPath(root, path), end: path === "", icon }),
  );
}

/** Menu items of the instance administration (superadmins only). */
export function adminNavItems(): NavItem<AdminArea>[] {
  return ADMIN_AREAS.map(({ key, path, icon }) => ({
    key,
    to: joinPath("/admin", path),
    end: false,
    icon,
  }));
}
