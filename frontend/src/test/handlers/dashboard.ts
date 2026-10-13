import { delay, http, HttpResponse } from "msw";

import type { InstanceDashboard, InstanceHealth } from "@/lib/api/adminDashboard";
import type { Me } from "@/lib/api/auth";
import type { WorkspaceDashboard } from "@/lib/api/dashboard";

import {
  makeInstanceDashboard,
  makeInstanceHealth,
  makeWorkspaceDashboard,
} from "../dashboardFactories";
import { makeMe, makeWorkspace } from "../factories";
import { apiErrorResponse } from "./errors";

const DASHBOARD = "*/v1/workspaces/:workspaceId/dashboard";
const ADMIN_DASHBOARD = "*/v1/admin/dashboard";
const ADMIN_HEALTH = "*/v1/admin/health";
const ENTER = "*/v1/admin/workspaces/:workspaceId/enter";
const ACCESS = "*/v1/admin/workspace-access";

/** GET .../dashboard answering with `dashboard` (default: `makeWorkspaceDashboard()`). */
export function workspaceDashboardAs(dashboard: WorkspaceDashboard = makeWorkspaceDashboard()) {
  return http.get(DASHBOARD, () => HttpResponse.json<WorkspaceDashboard>(dashboard));
}

/** GET .../dashboard failing on the server (500). */
export const workspaceDashboardServerError = http.get(DASHBOARD, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET .../dashboard that never answers, to see the loading state. */
export const workspaceDashboardPending = http.get(DASHBOARD, async () => {
  await delay("infinite");
  return HttpResponse.json(null);
});

/** GET /v1/admin/dashboard answering with `dashboard`. */
export function instanceDashboardAs(dashboard: InstanceDashboard = makeInstanceDashboard()) {
  return http.get(ADMIN_DASHBOARD, () => HttpResponse.json<InstanceDashboard>(dashboard));
}

/** GET /v1/admin/dashboard failing on the server (500). */
export const instanceDashboardServerError = http.get(ADMIN_DASHBOARD, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET /v1/admin/health answering with `health`. */
export function instanceHealthAs(health: InstanceHealth = makeInstanceHealth()) {
  return http.get(ADMIN_HEALTH, () => HttpResponse.json<InstanceHealth>(health));
}

/** GET /v1/admin/health failing on the server (500). */
export const instanceHealthServerError = http.get(ADMIN_HEALTH, () =>
  apiErrorResponse(500, "internal_error"),
);

/** `me` of a superadmin with access to workspace `id` (`name`), on top of `base`'s workspaces. */
export function meWithAccess(id: string, name: string, base: Me = makeMe({ is_superadmin: true })) {
  const others = base.workspaces.filter((workspace) => workspace.id !== id);
  return {
    ...base,
    is_superadmin: true,
    superadmin_access: {
      workspace_id: id,
      workspace_name: name,
      entered_at: "2026-10-10T11:30:00Z",
    },
    workspaces: [
      ...others,
      makeWorkspace({ id, name, slug: "acessado", role: "admin", access: "superadmin" }),
    ],
  } satisfies Me;
}

/**
 * Superadmin access that really changes: `me` (GET /v1/me) is `base` (the memberships, no access),
 * or already with the access to `startIn`; `enter` grants the access to the workspace of the path
 * (named by `names`) and the `DELETE` goes back to `base`. `entered` keeps the ids entered and
 * `left` counts the exits.
 */
export function workspaceAccessStore(
  base: Me = makeMe({ is_superadmin: true }),
  names: Record<string, string> = {},
  startIn?: string,
) {
  const nameOf = (workspaceId: string) => names[workspaceId] ?? "Workspace acessado";
  let me = startIn === undefined ? base : meWithAccess(startIn, nameOf(startIn), base);
  const entered: string[] = [];
  let left = 0;
  const handlers = [
    http.get("*/v1/me", () => HttpResponse.json<Me>(me)),
    http.post(ENTER, ({ params }) => {
      const workspaceId = String(params.workspaceId);
      entered.push(workspaceId);
      me = meWithAccess(workspaceId, nameOf(workspaceId), base);
      return HttpResponse.json<Me>(me);
    }),
    http.delete(ACCESS, () => {
      left += 1;
      me = base;
      return HttpResponse.json<Me>(me);
    }),
  ];
  return {
    handlers,
    entered,
    get left() {
      return left;
    },
  };
}

/** POST /v1/admin/workspaces/{id}/enter refused with `status` and `code`. */
export function enterWorkspaceFails(status: number, code: string) {
  return http.post(ENTER, () => apiErrorResponse(status, code));
}

/** DELETE /v1/admin/workspace-access refused with `status` and `code`. */
export function leaveWorkspaceAccessFails(status: number, code: string) {
  return http.delete(ACCESS, () => apiErrorResponse(status, code));
}

/** Default handlers: the default dashboards and health, and access changes answering `me`. */
export const dashboardHandlers = [
  workspaceDashboardAs(),
  instanceDashboardAs(),
  instanceHealthAs(),
  http.post(ENTER, ({ params }) =>
    HttpResponse.json<Me>(meWithAccess(String(params.workspaceId), "Workspace acessado")),
  ),
  http.delete(ACCESS, () => HttpResponse.json<Me>(makeMe({ is_superadmin: true }))),
];
