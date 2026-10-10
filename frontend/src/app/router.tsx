import { createBrowserRouter, type RouteObject } from "react-router";

import { RequireAuth } from "@/features/auth/RequireAuth";
import { RequireSetupDone } from "@/features/auth/RequireSetupDone";
import { RequireSuperadmin } from "@/features/auth/RequireSuperadmin";
import { RequireWorkspaceRole } from "@/features/auth/RequireWorkspaceRole";

import { HomePage } from "./HomePage";
import { Layout } from "./Layout";
import { NotFoundPage } from "./NotFoundPage";
import { PlaceholderPage } from "./PlaceholderPage";

// URLs in English (plan 0002, D11); the texts on screen come from i18n.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { path: "setup", element: <PlaceholderPage page="setup" /> },
      {
        element: <RequireSetupDone />,
        children: [
          { path: "login", element: <PlaceholderPage page="login" /> },
          { path: "forgot-password", element: <PlaceholderPage page="forgotPassword" /> },
          { path: "reset-password", element: <PlaceholderPage page="resetPassword" /> },
          { path: "verify-email", element: <PlaceholderPage page="verifyEmail" /> },
          { path: "accept-invitation", element: <PlaceholderPage page="acceptInvitation" /> },
          {
            element: <RequireAuth />,
            children: [
              { index: true, element: <HomePage /> },
              { path: "account/*", element: <PlaceholderPage page="account" /> },
              {
                path: "admin",
                element: <RequireSuperadmin />,
                children: [{ path: "*", element: <PlaceholderPage page="admin" /> }],
              },
              {
                path: "w/:workspaceId",
                element: <RequireWorkspaceRole />,
                children: [
                  { index: true, element: <PlaceholderPage page="workspace" /> },
                  {
                    path: "settings",
                    element: <RequireWorkspaceRole minRole="admin" />,
                    children: [
                      { path: "*", element: <PlaceholderPage page="workspaceSettings" /> },
                    ],
                  },
                ],
              },
            ],
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
