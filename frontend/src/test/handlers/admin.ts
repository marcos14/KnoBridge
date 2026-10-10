import { http, HttpResponse } from "msw";

import type {
  AdminUser,
  AdminWorkspace,
  CreatedWorkspace,
  CreateWorkspaceInput,
  UserChange,
  WorkspaceChange,
} from "@/lib/api/admin";

import {
  adminId,
  makeAdminUser,
  makeAdminUsers,
  makeAdminWorkspace,
  makeAdminWorkspaces,
  makeInvitation,
} from "../factories";
import { apiErrorResponse } from "./errors";
import { matchesQuery, page } from "./page";

const WORKSPACES = "*/v1/admin/workspaces";
const WORKSPACE = "*/v1/admin/workspaces/:workspaceId";
const USERS = "*/v1/admin/users";
const USER = "*/v1/admin/users/:userId";

/** Name, slug and owner of a workspace created by the fakes, with a fixed id and date. */
function createdWorkspace(body: CreateWorkspaceInput, index: number): CreatedWorkspace {
  const slug = body.slug ?? body.name.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-");
  return {
    workspace: makeAdminWorkspace({
      id: adminId(index),
      name: body.name,
      slug,
      member_count: 0,
      created_at: "2026-10-10T12:00:00Z",
    }),
    owner_invitation: makeInvitation({ email: body.owner_email, role: "owner" }),
  };
}

/** GET /v1/admin/workspaces listing `workspaces`, searched by `q` (name or slug) and paged. */
export function adminWorkspacesAs(workspaces: AdminWorkspace[] = makeAdminWorkspaces()) {
  return http.get(WORKSPACES, ({ request }) =>
    page(
      request,
      workspaces.filter((item) => matchesQuery(request, item.name, item.slug)),
    ),
  );
}

/**
 * Workspaces that really change: `POST` adds one (409 `slug_taken` for a slug in use) and
 * `PATCH` renames or changes the status. `created`, `changes` and `queries` keep what was asked.
 */
export function adminWorkspaceStore(initial: AdminWorkspace[] = makeAdminWorkspaces()) {
  let workspaces = [...initial];
  const created: CreateWorkspaceInput[] = [];
  const changes: { workspaceId: string; change: WorkspaceChange }[] = [];
  const queries: URLSearchParams[] = [];
  const handlers = [
    http.get(WORKSPACES, ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return page(
        request,
        workspaces.filter((item) => matchesQuery(request, item.name, item.slug)),
      );
    }),
    http.post(WORKSPACES, async ({ request }) => {
      const body = (await request.json()) as CreateWorkspaceInput;
      if (workspaces.some((item) => item.slug === body.slug)) {
        return apiErrorResponse(409, "slug_taken", { slug: body.slug });
      }
      const result = createdWorkspace(body, created.length);
      workspaces = [...workspaces, result.workspace];
      created.push(body);
      return HttpResponse.json<CreatedWorkspace>(result, { status: 201 });
    }),
    http.patch(WORKSPACE, async ({ params, request }) => {
      const workspaceId = String(params.workspaceId);
      const change = (await request.json()) as WorkspaceChange;
      const workspace = workspaces.find((item) => item.id === workspaceId);
      if (workspace === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const updated: AdminWorkspace = {
        ...workspace,
        name: change.name ?? workspace.name,
        status: change.status ?? workspace.status,
      };
      workspaces = workspaces.map((item) => (item.id === workspaceId ? updated : item));
      changes.push({ workspaceId, change });
      return HttpResponse.json<AdminWorkspace>(updated);
    }),
  ];
  return { handlers, created, changes, queries };
}

/** POST /v1/admin/workspaces refused with `status` and `code`. */
export function createWorkspaceFails(status: number, code: string) {
  return http.post(WORKSPACES, () => apiErrorResponse(status, code));
}

/** PATCH /v1/admin/workspaces/{id} refused with `status` and `code`. */
export function updateWorkspaceFails(status: number, code: string) {
  return http.patch(WORKSPACE, () => apiErrorResponse(status, code));
}

/** GET /v1/admin/workspaces failing on the server (500). */
export const adminWorkspacesServerError = http.get(WORKSPACES, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET /v1/admin/users listing `users`, searched by `q` (e-mail or name) and paged. */
export function adminUsersAs(users: AdminUser[] = makeAdminUsers()) {
  return http.get(USERS, ({ request }) =>
    page(
      request,
      users.filter((item) => matchesQuery(request, item.email, item.name)),
    ),
  );
}

/**
 * Users that really change: `PATCH` suspends, reactivates, grants or removes superadmin.
 * `changes` and `queries` keep what was asked, in order.
 */
export function adminUserStore(initial: AdminUser[] = makeAdminUsers()) {
  let users = [...initial];
  const changes: { userId: string; change: UserChange }[] = [];
  const queries: URLSearchParams[] = [];
  const handlers = [
    http.get(USERS, ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return page(
        request,
        users.filter((item) => matchesQuery(request, item.email, item.name)),
      );
    }),
    http.patch(USER, async ({ params, request }) => {
      const userId = String(params.userId);
      const change = (await request.json()) as UserChange;
      const user = users.find((item) => item.id === userId);
      if (user === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const updated: AdminUser = {
        ...user,
        status: change.status ?? user.status,
        is_superadmin: change.is_superadmin ?? user.is_superadmin,
      };
      users = users.map((item) => (item.id === userId ? updated : item));
      changes.push({ userId, change });
      return HttpResponse.json<AdminUser>(updated);
    }),
  ];
  return { handlers, changes, queries };
}

/** PATCH /v1/admin/users/{id} refused with `status` and `code`. */
export function updateUserFails(status: number, code: string) {
  return http.patch(USER, () => apiErrorResponse(status, code));
}

/** GET /v1/admin/users failing on the server (500). */
export const adminUsersServerError = http.get(USERS, () => apiErrorResponse(500, "internal_error"));

/** Default handlers: the default lists, and mutations answering with the changed row. */
export const adminHandlers = [
  adminWorkspacesAs(),
  http.post(WORKSPACES, async ({ request }) => {
    const body = (await request.json()) as CreateWorkspaceInput;
    return HttpResponse.json<CreatedWorkspace>(createdWorkspace(body, 0), { status: 201 });
  }),
  http.patch(WORKSPACE, async ({ request }) => {
    const change = (await request.json()) as WorkspaceChange;
    const workspace = makeAdminWorkspace();
    return HttpResponse.json<AdminWorkspace>({
      ...workspace,
      name: change.name ?? workspace.name,
      status: change.status ?? workspace.status,
    });
  }),
  adminUsersAs(),
  http.patch(USER, async ({ request }) => {
    const change = (await request.json()) as UserChange;
    const user = makeAdminUser();
    return HttpResponse.json<AdminUser>({
      ...user,
      status: change.status ?? user.status,
      is_superadmin: change.is_superadmin ?? user.is_superadmin,
    });
  }),
];
