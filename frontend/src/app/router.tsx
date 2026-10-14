import type { ReactNode } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { RequireAuth } from "@/features/auth/RequireAuth";
import { RequireSetupDone } from "@/features/auth/RequireSetupDone";
import { RequireSetupPending } from "@/features/auth/RequireSetupPending";
import { RequireSuperadmin } from "@/features/auth/RequireSuperadmin";
import { RequireWorkspaceRole } from "@/features/auth/RequireWorkspaceRole";

import { HomePage } from "./HomePage";
import { Layout } from "./Layout";
import { NotFoundPage } from "./NotFoundPage";
import { lazyPage } from "./lazyPage";
import { PublicLayout } from "./PublicLayout";
import { AppShell } from "./shell/AppShell";
import { AreaSkeletonPage } from "./shell/AreaSkeletonPage";
import { HomeRedirect } from "./shell/HomeRedirect";
import { areaMinRole, areaPath, type WorkspaceArea } from "./shell/navItems";
import { WorkspaceLayout } from "./shell/WorkspaceLayout";

// Elements of the feature pages, each loaded on its first visit (code splitting); guards and
// layouts stay in the main chunk.
const ProfilePage = lazyPage(() =>
  import("@/features/account/ProfilePage").then((m) => m.ProfilePage),
);
const SecurityPage = lazyPage(() =>
  import("@/features/account/SecurityPage").then((m) => m.SecurityPage),
);
const AdminUsersPage = lazyPage(() =>
  import("@/features/admin/AdminUsersPage").then((m) => m.AdminUsersPage),
);
const InstanceDashboardPage = lazyPage(() =>
  import("@/features/admin/InstanceDashboardPage").then((m) => m.InstanceDashboardPage),
);
const AdminWorkspacesPage = lazyPage(() =>
  import("@/features/admin/AdminWorkspacesPage").then((m) => m.AdminWorkspacesPage),
);
const ApiKeysPage = lazyPage(() =>
  import("@/features/apikeys/ApiKeysPage").then((m) => m.ApiKeysPage),
);
const ProductsPage = lazyPage(() =>
  import("@/features/products/ProductsPage").then((m) => m.ProductsPage),
);
const InstanceAuditPage = lazyPage(() =>
  import("@/features/audit/InstanceAuditPage").then((m) => m.InstanceAuditPage),
);
const WorkspaceAuditPage = lazyPage(() =>
  import("@/features/audit/WorkspaceAuditPage").then((m) => m.WorkspaceAuditPage),
);
const AcceptInvitationPage = lazyPage(() =>
  import("@/features/auth/AcceptInvitationPage").then((m) => m.AcceptInvitationPage),
);
const ForgotPasswordPage = lazyPage(() =>
  import("@/features/auth/ForgotPasswordPage").then((m) => m.ForgotPasswordPage),
);
const LoginPage = lazyPage(() => import("@/features/auth/LoginPage").then((m) => m.LoginPage));
const ResetPasswordPage = lazyPage(() =>
  import("@/features/auth/ResetPasswordPage").then((m) => m.ResetPasswordPage),
);
const SetupPage = lazyPage(() => import("@/features/auth/SetupPage").then((m) => m.SetupPage));
const VerifyEmailPage = lazyPage(() =>
  import("@/features/auth/VerifyEmailPage").then((m) => m.VerifyEmailPage),
);
const ChatPage = lazyPage(() => import("@/features/chat/ChatPage").then((m) => m.ChatPage));
const CollectionsPage = lazyPage(() =>
  import("@/features/collections/CollectionsPage").then((m) => m.CollectionsPage),
);
const ConversationsPage = lazyPage(() =>
  import("@/features/conversations/ConversationsPage").then((m) => m.ConversationsPage),
);
const MembersPage = lazyPage(() =>
  import("@/features/members/MembersPage").then((m) => m.MembersPage),
);
const ProvidersPage = lazyPage(() =>
  import("@/features/providers/ProvidersPage").then((m) => m.ProvidersPage),
);
const RunnersPage = lazyPage(() =>
  import("@/features/runners/RunnersPage").then((m) => m.RunnersPage),
);
const SourcesPage = lazyPage(() =>
  import("@/features/sources/SourcesPage").then((m) => m.SourcesPage),
);
const UsagePage = lazyPage(() => import("@/features/usage/UsagePage").then((m) => m.UsagePage));
const WidgetsPage = lazyPage(() =>
  import("@/features/widget/WidgetsPage").then((m) => m.WidgetsPage),
);
const WorkspaceSettingsPage = lazyPage(() =>
  import("@/features/settings/WorkspaceSettingsPage").then((m) => m.WorkspaceSettingsPage),
);

/**
 * Route of a workspace area (`/w/:workspaceId/<path of the area>`), guarded by the role the menu uses for
 * the same area (`WORKSPACE_AREAS`), so a hidden item is also a closed route. `subPaths` (e.g.
 * `:conversationId`) are served by the same element, which stays mounted while the URL moves
 * between them; other sub-pages are a 404.
 */
function workspaceArea(
  area: Exclude<WorkspaceArea, "home">,
  element: ReactNode,
  subPaths: readonly string[] = [],
): RouteObject {
  return {
    path: areaPath(area),
    element: <RequireWorkspaceRole minRole={areaMinRole(area)} />,
    children:
      subPaths.length === 0
        ? [{ index: true, element }]
        : [{ element, children: [{ index: true }, ...subPaths.map((path) => ({ path }))] }],
  };
}

// URLs in English (plan 0002, D11); the texts on screen come from i18n.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      {
        element: <PublicLayout />,
        children: [
          {
            path: "setup",
            element: <RequireSetupPending />,
            children: [{ index: true, element: SetupPage }],
          },
        ],
      },
      {
        element: <RequireSetupDone />,
        children: [
          {
            element: <PublicLayout />,
            children: [
              { path: "login", element: LoginPage },
              { path: "forgot-password", element: ForgotPasswordPage },
              { path: "reset-password", element: ResetPasswordPage },
              { path: "verify-email", element: VerifyEmailPage },
              { path: "accept-invitation", element: AcceptInvitationPage },
            ],
          },
          {
            element: <RequireAuth />,
            children: [
              {
                element: <AppShell />,
                children: [
                  { index: true, element: <HomeRedirect /> },
                  {
                    path: "account",
                    children: [
                      { index: true, element: <Navigate to="profile" replace /> },
                      { path: "profile", element: ProfilePage },
                      { path: "security", element: SecurityPage },
                    ],
                  },
                  {
                    path: "admin",
                    element: <RequireSuperadmin />,
                    children: [
                      { index: true, element: InstanceDashboardPage },
                      { path: "workspaces", element: AdminWorkspacesPage },
                      { path: "users", element: AdminUsersPage },
                      { path: "audit", element: InstanceAuditPage },
                    ],
                  },
                  {
                    path: "w/:workspaceId",
                    element: <RequireWorkspaceRole />,
                    children: [
                      {
                        element: <WorkspaceLayout />,
                        children: [
                          { index: true, element: <HomePage /> },
                          workspaceArea("chat", ChatPage, [":conversationId"]),
                          workspaceArea("conversations", ConversationsPage, [":conversationId"]),
                          workspaceArea("usage", UsagePage),
                          workspaceArea("products", ProductsPage),
                          // Old address of the screen (plan 0009 turned assistants into products).
                          { path: "assistants", element: <Navigate to="../products" replace /> },
                          workspaceArea("providers", ProvidersPage),
                          workspaceArea("sources", SourcesPage, [":sourceId"]),
                          workspaceArea("runners", RunnersPage),
                          workspaceArea("apiKeys", ApiKeysPage),
                          workspaceArea("widgets", WidgetsPage, [":widgetId"]),
                          workspaceArea("pipelines", <AreaSkeletonPage area="pipelines" />),
                          workspaceArea("collections", CollectionsPage, [":collectionId"]),
                          workspaceArea("channels", <AreaSkeletonPage area="channels" />),
                          workspaceArea("members", MembersPage),
                          workspaceArea("settings", WorkspaceSettingsPage),
                          workspaceArea("audit", WorkspaceAuditPage),
                          { path: "*", element: <NotFoundPage /> },
                        ],
                      },
                    ],
                  },
                  { path: "*", element: <NotFoundPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
