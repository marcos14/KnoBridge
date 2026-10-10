import { http, HttpResponse } from "msw";

import type { Session } from "@/lib/api/account";

import { makeSessions } from "../factories";
import { apiErrorResponse } from "./errors";

const SESSIONS = "*/v1/me/sessions";
const SESSION = "*/v1/me/sessions/:sessionId";
const PASSWORD = "*/v1/me/password";
const RESEND = "*/v1/auth/email/resend";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** Answers `GET /v1/me/sessions` with one page of `sessions`, honouring `limit` and `offset`. */
function sessionPage(request: Request, sessions: Session[]) {
  const query = new URL(request.url).searchParams;
  const limit = Number(query.get("limit") ?? "50");
  const offset = Number(query.get("offset") ?? "0");
  return HttpResponse.json({
    items: sessions.slice(offset, offset + limit),
    total: sessions.length,
    limit,
    offset,
  });
}

/** GET /v1/me/sessions listing `sessions` (default: this one and a phone). */
export function sessionsAs(sessions: Session[] = makeSessions()) {
  return http.get(SESSIONS, ({ request }) => sessionPage(request, sessions));
}

/**
 * Sessions that really end: `DELETE /v1/me/sessions/{id}` removes the session from the list the
 * next `GET` returns (404 when it is not there). `revoked` keeps the ids, in order.
 */
export function sessionStore(initial: Session[] = makeSessions()) {
  let sessions = [...initial];
  const revoked: string[] = [];
  const handlers = [
    http.get(SESSIONS, ({ request }) => sessionPage(request, sessions)),
    http.delete(SESSION, ({ params }) => {
      const id = String(params.sessionId);
      if (!sessions.some((session) => session.id === id)) {
        return apiErrorResponse(404, "not_found");
      }
      sessions = sessions.filter((session) => session.id !== id);
      revoked.push(id);
      return noContent();
    }),
  ];
  return { handlers, revoked };
}

/** GET /v1/me/sessions with the default list. */
export const sessionsOk = sessionsAs();

/** GET /v1/me/sessions failing on the server (500). */
export const sessionsServerError = http.get(SESSIONS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** DELETE /v1/me/sessions/{id} ending the session (204). */
export const revokeSessionOk = http.delete(SESSION, noContent);

/** DELETE /v1/me/sessions/{id} rejected by the CSRF check (403). */
export const revokeSessionCsrfFailed = http.delete(SESSION, () =>
  apiErrorResponse(403, "csrf_failed"),
);

/** POST /v1/me/password accepting the change (204). */
export const changePasswordOk = http.post(PASSWORD, noContent);

/** POST /v1/me/password with a wrong current password (422). */
export const changePasswordInvalidCurrent = http.post(PASSWORD, () =>
  apiErrorResponse(422, "invalid_current_password"),
);

/** POST /v1/me/password with a new password the backend refuses (422). */
export const changePasswordWeak = http.post(PASSWORD, () => apiErrorResponse(422, "weak_password"));

/** POST /v1/auth/email/resend sending a new link (204). */
export const resendVerificationOk = http.post(RESEND, noContent);

/** POST /v1/auth/email/resend when the address is already verified (409). */
export const resendVerificationAlreadyVerified = http.post(RESEND, () =>
  apiErrorResponse(409, "email_already_verified"),
);

/** POST /v1/auth/email/resend over the limit (429), asking to wait `seconds`. */
export function resendVerificationTooMany(seconds: number | null = 120) {
  return http.post(RESEND, () =>
    apiErrorResponse(
      429,
      "too_many_attempts",
      seconds === null ? null : { retry_after_seconds: seconds },
    ),
  );
}

export const accountHandlers = [
  sessionsOk,
  revokeSessionOk,
  changePasswordOk,
  resendVerificationOk,
];
