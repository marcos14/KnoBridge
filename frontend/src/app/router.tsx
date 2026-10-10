import type { ReactNode } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

import { ProfilePage } from "@/features/account/ProfilePage";
import { SecurityPage } from "@/features/account/SecurityPage";
import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { AdminWorkspacesPage } from "@/features/admin/AdminWorkspacesPage";
import { AssistantsPage } from "@/features/assistants/AssistantsPage";
import { InstanceAuditPage } from "@/features/audit/InstanceAuditPage";
import { WorkspaceAuditPage } from "@/features/audit/WorkspaceAuditPage";
import { AcceptInvitationPage } from "@/features/auth/AcceptInvitationPage";
import { ForgotPasswordPage } from "@/features/auth/ForgotPasswordPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/RequireAuth";
import { RequireSetupDone } from "@/features/auth/RequireSetupDone";
import { RequireSetupPending } from "@/features/auth/RequireSetupPending";
import { RequireSuperadmin } from "@/features/auth/RequireSuperadmin";
import { RequireWorkspaceRole } from "@/features/auth/RequireWorkspaceRole";
import { ResetPasswordPage } from "@/features/auth/ResetPasswordPage";
import { SetupPage } from "@/features/auth/SetupPage";
import { VerifyEmailPage } from "@/features/auth/VerifyEmailPage";
import { ChatPage } from "@/features/chat/ChatPage";
import { MembersPage } from "@/features/members/MembersPage";
import { ProvidersPage } from "@/features/providers/ProvidersPage";
import { WorkspaceSettingsPage } from "@/features/settings/WorkspaceSettingsPage";

import { HomePage } from "./HomePage";
import { Layout } from "./Layout";
import { NotFoundPage } from "./NotFoundPage";
import { PlaceholderPage } from "./PlaceholderPage";
import { PublicLayout } from "./PublicLayout";
import { AppShell } from "./shell/AppShell";
import { AreaSkeletonPage } from "./shell/AreaSkeletonPage";
import { HomeRedirect } from "./shell/HomeRedirect";
import { areaMinRole, type WorkspaceArea } from "./shell/navItems";
import { WorkspaceLayout } from "./shell/WorkspaceLayout";

/**
 * Route of a workspace area (`/w/:workspaceId/<area>`), guarded by the role the menu uses for
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
    path: area,
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
            children: [{ index: true, element: <SetupPage /> }],
          },
        ],
      },
      {
        element: <RequireSetupDone />,
        children: [
          {
            element: <PublicLayout />,
            children: [
              { path: "login", element: <LoginPage /> },
              { path: "forgot-password", element: <ForgotPasswordPage /> },
              { path: "reset-password", element: <ResetPasswordPage /> },
              { path: "verify-email", element: <VerifyEmailPage /> },
              { path: "accept-invitation", element: <AcceptInvitationPage /> },
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
                      { path: "profile", element: <ProfilePage /> },
                      { path: "security", element: <SecurityPage /> },
                    ],
                  },
                  {
                    path: "admin",
                    element: <RequireSuperadmin />,
                    children: [
                      { index: true, element: <Navigate to="workspaces" replace /> },
                      { path: "workspaces", element: <AdminWorkspacesPage /> },
                      { path: "users", element: <AdminUsersPage /> },
                      { path: "audit", element: <InstanceAuditPage /> },
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
                          workspaceArea("chat", <ChatPage />, [":conversationId"]),
                          workspaceArea("conversations", <PlaceholderPage page="conversations" />),
                          workspaceArea("assistants", <AssistantsPage />),
                          workspaceArea("providers", <ProvidersPage />),
                          workspaceArea("sources", <AreaSkeletonPage area="sources" />),
                          workspaceArea("pipelines", <AreaSkeletonPage area="pipelines" />),
                          workspaceArea("collections", <AreaSkeletonPage area="collections" />),
                          workspaceArea("channels", <AreaSkeletonPage area="channels" />),
                          workspaceArea("members", <MembersPage />),
                          workspaceArea("settings", <WorkspaceSettingsPage />),
                          workspaceArea("audit", <WorkspaceAuditPage />),
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
