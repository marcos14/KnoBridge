import { http, HttpResponse } from "msw";

import type { Invitation, InviteInput } from "@/lib/api/invites";
import type { Member } from "@/lib/api/members";
import type { Workspace } from "@/lib/api/workspaces";

import {
  makeInvitation,
  makeInvitations,
  makeMember,
  makeMembers,
  makeWorkspace,
} from "../factories";
import { apiErrorResponse } from "./errors";

const WORKSPACE = "*/v1/workspaces/:workspaceId";
const MEMBERS = "*/v1/workspaces/:workspaceId/members";
const MEMBER = "*/v1/workspaces/:workspaceId/members/:userId";
const INVITES = "*/v1/workspaces/:workspaceId/invites";
const INVITE = "*/v1/workspaces/:workspaceId/invites/:invitationId";
const RESEND = "*/v1/workspaces/:workspaceId/invites/:invitationId/resend";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** One page of `rows`, honouring `limit` and `offset` like the API (default limit 50). */
function page(request: Request, rows: readonly unknown[]) {
  const query = new URL(request.url).searchParams;
  const limit = Number(query.get("limit") ?? "50");
  const offset = Number(query.get("offset") ?? "0");
  return HttpResponse.json({
    items: rows.slice(offset, offset + limit),
    total: rows.length,
    limit,
    offset,
  });
}

/** GET /v1/workspaces/{id}/members listing `members` (default: Ana, Bruno, Carla and Davi). */
export function membersAs(members: Member[] = makeMembers()) {
  return http.get(MEMBERS, ({ request }) => page(request, members));
}

/**
 * Members that really change: `PATCH` updates the role and `DELETE` removes the member from the
 * next `GET` (404 for an unknown id). `changes` and `removed` keep what was asked, in order.
 */
export function memberStore(initial: Member[] = makeMembers()) {
  let members = [...initial];
  const changes: { userId: string; role: string }[] = [];
  const removed: string[] = [];
  const handlers = [
    http.get(MEMBERS, ({ request }) => page(request, members)),
    http.patch(MEMBER, async ({ params, request }) => {
      const userId = String(params.userId);
      const { role } = (await request.json()) as Pick<Member, "role">;
      const member = members.find((item) => item.user_id === userId);
      if (member === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const updated = { ...member, role };
      members = members.map((item) => (item.user_id === userId ? updated : item));
      changes.push({ userId, role });
      return HttpResponse.json<Member>(updated);
    }),
    http.delete(MEMBER, ({ params }) => {
      const userId = String(params.userId);
      if (!members.some((item) => item.user_id === userId)) {
        return apiErrorResponse(404, "not_found");
      }
      members = members.filter((item) => item.user_id !== userId);
      removed.push(userId);
      return noContent();
    }),
  ];
  return { handlers, changes, removed };
}

/** GET /v1/workspaces/{id}/members with the default list. */
export const membersOk = membersAs();

/** GET /v1/workspaces/{id}/members failing on the server (500). */
export const membersServerError = http.get(MEMBERS, () => apiErrorResponse(500, "internal_error"));

/** PATCH /v1/workspaces/{id}/members/{user_id} answering with the default member in the new role. */
export const changeMemberRoleOk = http.patch(MEMBER, async ({ params, request }) => {
  const { role } = (await request.json()) as Pick<Member, "role">;
  const member = makeMembers().find((item) => item.user_id === String(params.userId));
  return HttpResponse.json<Member>({ ...(member ?? makeMember()), role });
});

/** PATCH /v1/workspaces/{id}/members/{user_id} refused with `status` and `code`. */
export function changeMemberRoleFails(status: number, code: string) {
  return http.patch(MEMBER, () => apiErrorResponse(status, code));
}

/** DELETE /v1/workspaces/{id}/members/{user_id} removing the member (204). */
export const removeMemberOk = http.delete(MEMBER, noContent);

/** DELETE /v1/workspaces/{id}/members/{user_id} refused with `status` and `code`. */
export function removeMemberFails(status: number, code: string) {
  return http.delete(MEMBER, () => apiErrorResponse(status, code));
}

/** GET /v1/workspaces/{id}/invites listing `invitations` (default: Elisa and Fábio, expired). */
export function invitesAs(invitations: Invitation[] = makeInvitations()) {
  return http.get(INVITES, ({ request }) => page(request, invitations));
}

/**
 * Invitations that really change: `POST` adds one first (replacing a pending one to the same
 * address), `DELETE` removes it and `resend` renews its validity. `created`, `revoked` and
 * `resent` keep what was asked, in order.
 */
export function inviteStore(initial: Invitation[] = makeInvitations()) {
  let invitations = [...initial];
  const created: InviteInput[] = [];
  const revoked: string[] = [];
  const resent: string[] = [];
  const find = (id: string) => invitations.find((item) => item.id === id);
  const handlers = [
    http.get(INVITES, ({ request }) => page(request, invitations)),
    http.post(INVITES, async ({ request }) => {
      const body = (await request.json()) as InviteInput;
      const invitation = makeInvitation({
        id: `00000000-0000-4000-8000-${String(900 + created.length).padStart(12, "0")}`,
        email: body.email,
        role: body.role,
      });
      invitations = [invitation, ...invitations.filter((item) => item.email !== body.email)];
      created.push(body);
      return HttpResponse.json<Invitation>(invitation, { status: 201 });
    }),
    http.delete(INVITE, ({ params }) => {
      const id = String(params.invitationId);
      if (find(id) === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      invitations = invitations.filter((item) => item.id !== id);
      revoked.push(id);
      return noContent();
    }),
    http.post(RESEND, ({ params }) => {
      const id = String(params.invitationId);
      const invitation = find(id);
      if (invitation === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const renewed = { ...invitation, expired: false, expires_at: "2026-10-17T12:00:00Z" };
      invitations = invitations.map((item) => (item.id === id ? renewed : item));
      resent.push(id);
      return HttpResponse.json<Invitation>(renewed);
    }),
  ];
  return { handlers, created, revoked, resent };
}

/** GET /v1/workspaces/{id}/invites with the default list. */
export const invitesOk = invitesAs();

/** GET /v1/workspaces/{id}/invites failing on the server (500). */
export const invitesServerError = http.get(INVITES, () => apiErrorResponse(500, "internal_error"));

/** POST /v1/workspaces/{id}/invites creating the invitation (201). */
export const createInviteOk = http.post(INVITES, async ({ request }) => {
  const body = (await request.json()) as InviteInput;
  return HttpResponse.json<Invitation>(makeInvitation(body), { status: 201 });
});

/** POST /v1/workspaces/{id}/invites refused with `status` and `code`. */
export function createInviteFails(status: number, code: string) {
  return http.post(INVITES, () => apiErrorResponse(status, code));
}

/** DELETE /v1/workspaces/{id}/invites/{invitation_id} revoking it (204). */
export const revokeInviteOk = http.delete(INVITE, noContent);

/** DELETE /v1/workspaces/{id}/invites/{invitation_id} refused with `status` and `code`. */
export function revokeInviteFails(status: number, code: string) {
  return http.delete(INVITE, () => apiErrorResponse(status, code));
}

/** POST /v1/workspaces/{id}/invites/{invitation_id}/resend renewing it. */
export const resendInviteOk = http.post(RESEND, () =>
  HttpResponse.json<Invitation>(makeInvitation()),
);

/** POST /v1/workspaces/{id}/invites/{invitation_id}/resend refused with `status` and `code`. */
export function resendInviteFails(status: number, code: string) {
  return http.post(RESEND, () => apiErrorResponse(status, code));
}

/** PATCH /v1/workspaces/{id} renaming the default workspace to the name sent. */
export const renameWorkspaceOk = http.patch(WORKSPACE, async ({ params, request }) => {
  const { name } = (await request.json()) as Pick<Workspace, "name">;
  const { slug, status } = makeWorkspace();
  return HttpResponse.json<Workspace>({ id: String(params.workspaceId), name, slug, status });
});

/** PATCH /v1/workspaces/{id} refused with `status` and `code`. */
export function renameWorkspaceFails(status: number, code: string) {
  return http.patch(WORKSPACE, () => apiErrorResponse(status, code));
}

export const membersHandlers = [
  membersOk,
  changeMemberRoleOk,
  removeMemberOk,
  invitesOk,
  createInviteOk,
  revokeInviteOk,
  resendInviteOk,
  renameWorkspaceOk,
];
