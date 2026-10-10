import { http, HttpResponse } from "msw";

import type { Me } from "@/lib/api/auth";
import type { SetupStatus } from "@/lib/api/setup";

import { makeMe } from "../factories";
import { apiErrorResponse } from "./errors";

const STATUS = "*/v1/setup/status";
const SETUP = "*/v1/setup";

/** GET /v1/setup/status for an instance already set up. */
export const setupStatusDone = http.get(STATUS, () =>
  HttpResponse.json<SetupStatus>({ needs_setup: false }),
);

/** GET /v1/setup/status for a fresh instance (no user yet). */
export const setupStatusNeeded = http.get(STATUS, () =>
  HttpResponse.json<SetupStatus>({ needs_setup: true }),
);

/** GET /v1/setup/status failing on the server (500). */
export const setupStatusServerError = http.get(STATUS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** POST /v1/setup creating the first superadmin (201, body of GET /v1/me). */
export const setupOk = http.post(SETUP, () =>
  HttpResponse.json<Me>(makeMe({ is_superadmin: true, workspaces: [] }), { status: 201 }),
);

/** POST /v1/setup on an instance already set up (409). */
export const setupAlreadyCompleted = http.post(SETUP, () =>
  apiErrorResponse(409, "setup_already_completed"),
);

export const setupHandlers = [setupStatusDone, setupOk];
