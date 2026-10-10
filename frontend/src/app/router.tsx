import type { ReactNode } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router";

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
 * the same area (`WORKSPACE_AREAS`), so a hidden item is also a closed route.
 */
function workspaceArea(area: Exclude<WorkspaceArea, "home">, element: ReactNode): RouteObject {
  return {
    path: area,
    element: <RequireWorkspaceRole minRole={areaMinRole(area)} />,
    // Sub-pages (e.g. a source's detail) arrive with each feature; until then they are a 404.
    children: [{ index: true, element }],
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
                      { path: "profile", element: <PlaceholderPage page="accountProfile" /> },
                      { path: "security", element: <PlaceholderPage page="accountSecurity" /> },
                    ],
                  },
                  {
                    path: "admin",
                    element: <RequireSuperadmin />,
                    children: [
                      { index: true, element: <Navigate to="workspaces" replace /> },
                      { path: "workspaces", element: <PlaceholderPage page="adminWorkspaces" /> },
                      { path: "users", element: <PlaceholderPage page="adminUsers" /> },
                      { path: "audit", element: <PlaceholderPage page="adminAudit" /> },
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
                          workspaceArea("chat", <PlaceholderPage page="chat" />),
                          workspaceArea("conversations", <PlaceholderPage page="conversations" />),
                          workspaceArea("assistants", <PlaceholderPage page="assistants" />),
                          workspaceArea("providers", <PlaceholderPage page="providers" />),
                          workspaceArea("sources", <AreaSkeletonPage area="sources" />),
                          workspaceArea("pipelines", <AreaSkeletonPage area="pipelines" />),
                          workspaceArea("collections", <AreaSkeletonPage area="collections" />),
                          workspaceArea("channels", <AreaSkeletonPage area="channels" />),
                          workspaceArea("members", <PlaceholderPage page="members" />),
                          workspaceArea("settings", <PlaceholderPage page="workspaceSettings" />),
                          workspaceArea("audit", <PlaceholderPage page="audit" />),
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
