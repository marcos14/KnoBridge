import { http, HttpResponse } from "msw";

import type { Me } from "@/lib/api/auth";
import type { InvitationPreview } from "@/lib/api/invites";

import { makeInvitationPreview, makeMe, makeWorkspace } from "../factories";
import { apiErrorResponse } from "./errors";

const PREVIEW = "*/v1/invites/preview";
const ACCEPT = "*/v1/invites/accept";

/** POST /v1/invites/preview answering with `preview` (default: invitation to a new address). */
export function invitationPreviewAs(preview: InvitationPreview = makeInvitationPreview()) {
  return http.post(PREVIEW, () => HttpResponse.json<InvitationPreview>(preview));
}

/** POST /v1/invites/preview for an address with no account yet. */
export const invitationPreviewOk = invitationPreviewAs();

/** POST /v1/invites/preview with an invalid, expired, used or revoked invitation (400). */
export const invitationPreviewInvalidToken = http.post(PREVIEW, () =>
  apiErrorResponse(400, "invalid_token"),
);

/**
 * POST /v1/invites/accept joining the workspace; answers like GET /v1/me for the invitee, now an
 * editor of the default workspace.
 */
export const acceptInvitationOk = http.post(ACCEPT, () =>
  HttpResponse.json<Me>(
    makeMe({
      user: { ...makeMe().user, email: makeInvitationPreview().email, name: "Bruno Teste" },
      workspaces: [makeWorkspace({ role: "editor" })],
    }),
  ),
);

/** POST /v1/invites/accept for an address with an account, without being logged in (401). */
export const acceptInvitationLoginRequired = http.post(ACCEPT, () =>
  apiErrorResponse(401, "login_required"),
);

/** POST /v1/invites/accept while logged in as another address (403). */
export const acceptInvitationEmailMismatch = http.post(ACCEPT, () =>
  apiErrorResponse(403, "invitation_email_mismatch"),
);

/** POST /v1/invites/accept with an invitation spent or revoked in the meantime (400). */
export const acceptInvitationInvalidToken = http.post(ACCEPT, () =>
  apiErrorResponse(400, "invalid_token"),
);

/** POST /v1/invites/accept when the user already belongs to the workspace (409). */
export const acceptInvitationAlreadyMember = http.post(ACCEPT, () =>
  apiErrorResponse(409, "already_member"),
);

export const invitesHandlers = [invitationPreviewOk, acceptInvitationOk];
