import { http, HttpResponse } from "msw";

import type { Me, ProfileUpdate } from "@/lib/api/auth";

import { makeMe } from "../factories";
import { apiErrorResponse } from "./errors";

const ME = "*/v1/me";
const LOGIN = "*/v1/auth/login";
const LOGOUT = "*/v1/auth/logout";
const CSRF = "*/v1/auth/csrf";

/** GET /v1/me answering with `me` (default: `makeMe()`). */
export function meAs(me: Me = makeMe()) {
  return http.get(ME, () => HttpResponse.json<Me>(me));
}

/** GET /v1/me with a live session: verified owner of one workspace. */
export const meOk = meAs();

/** GET /v1/me without a session (401). */
export const meUnauthenticated = http.get(ME, () => apiErrorResponse(401, "unauthenticated"));

/** GET /v1/me failing on the server (500). */
export const meServerError = http.get(ME, () => apiErrorResponse(500, "internal_error"));

/**
 * PATCH /v1/me applying the body to the default user and answering like GET /v1/me; omitted or
 * null fields keep their value, as in the backend.
 */
export const updateProfileOk = http.patch(ME, async ({ request }) => {
  const body = (await request.json()) as ProfileUpdate;
  const me = makeMe();
  const user = {
    ...me.user,
    name: body.name ?? me.user.name,
    locale: body.locale ?? me.user.locale,
    theme: body.theme ?? me.user.theme,
  };
  return HttpResponse.json<Me>({ ...me, user });
});

/** PATCH /v1/me rejected by the CSRF check (403). */
export const updateProfileCsrfFailed = http.patch(ME, () => apiErrorResponse(403, "csrf_failed"));

/** POST /v1/auth/login accepting any credentials and answering like GET /v1/me. */
export const loginOk = http.post(LOGIN, () => HttpResponse.json<Me>(makeMe()));

/** POST /v1/auth/login with wrong credentials (401, generic on purpose). */
export const loginInvalidCredentials = http.post(LOGIN, () =>
  apiErrorResponse(401, "invalid_credentials"),
);

/** POST /v1/auth/logout ending the session (204). */
export const logoutOk = http.post(LOGOUT, () => new HttpResponse(null, { status: 204 }));

/** POST /v1/auth/logout when the session had already ended (401). */
export const logoutUnauthenticated = http.post(LOGOUT, () =>
  apiErrorResponse(401, "unauthenticated"),
);

/** POST /v1/auth/logout rejected by the CSRF check (403). */
export const logoutCsrfFailed = http.post(LOGOUT, () => apiErrorResponse(403, "csrf_failed"));

/** GET /v1/auth/csrf issuing a synthetic token. */
export const csrfOk = http.get(CSRF, () =>
  HttpResponse.json({ csrf_token: "synthetic-nonce.synthetic-signature" }),
);

export const authHandlers = [meOk, updateProfileOk, loginOk, logoutOk, csrfOk];
