import { http, HttpResponse } from "msw";

import { apiErrorResponse } from "./errors";

const FORGOT = "*/v1/auth/password/forgot";
const RESET = "*/v1/auth/password/reset";
const VERIFY = "*/v1/auth/email/verify";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** POST /v1/auth/password/forgot (always 204, known address or not). */
export const forgotPasswordOk = http.post(FORGOT, noContent);

/** POST /v1/auth/password/forgot failing on the server (500). */
export const forgotPasswordServerError = http.post(FORGOT, () =>
  apiErrorResponse(500, "internal_error"),
);

/** POST /v1/auth/password/reset accepting the token and the new password (204). */
export const resetPasswordOk = http.post(RESET, noContent);

/** POST /v1/auth/password/reset with an invalid, expired or used token (400). */
export const resetPasswordInvalidToken = http.post(RESET, () =>
  apiErrorResponse(400, "invalid_token"),
);

/** POST /v1/auth/password/reset with a password the backend refuses (422). */
export const resetPasswordWeak = http.post(RESET, () => apiErrorResponse(422, "weak_password"));

/** POST /v1/auth/email/verify accepting the token (204). */
export const verifyEmailOk = http.post(VERIFY, noContent);

/** POST /v1/auth/email/verify with an invalid, expired or used token (400). */
export const verifyEmailInvalidToken = http.post(VERIFY, () =>
  apiErrorResponse(400, "invalid_token"),
);

/** POST /v1/auth/email/verify failing on the server (500). */
export const verifyEmailServerError = http.post(VERIFY, () =>
  apiErrorResponse(500, "internal_error"),
);

export const recoveryHandlers = [forgotPasswordOk, resetPasswordOk, verifyEmailOk];
