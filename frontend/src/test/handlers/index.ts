import { accountHandlers } from "./account";
import { adminHandlers } from "./admin";
import { assistantsHandlers } from "./assistants";
import { auditHandlers } from "./audit";
import { authHandlers } from "./auth";
import { healthReadyOk } from "./health";
import { invitesHandlers } from "./invites";
import { membersHandlers } from "./members";
import { providersHandlers } from "./providers";
import { recoveryHandlers } from "./recovery";
import { setupHandlers } from "./setup";

export * from "./account";
export * from "./admin";
export * from "./assistants";
export * from "./audit";
export * from "./auth";
export * from "./errors";
export * from "./health";
export * from "./invites";
export * from "./members";
export * from "./page";
export * from "./providers";
export * from "./record";
export * from "./recovery";
export * from "./setup";

/**
 * Default handlers: the happy path of a set-up instance with a logged-in user. Override per test
 * with `server.use(...)`.
 */
export const handlers = [
  healthReadyOk,
  ...setupHandlers,
  ...authHandlers,
  ...recoveryHandlers,
  ...invitesHandlers,
  ...accountHandlers,
  ...membersHandlers,
  ...auditHandlers,
  ...adminHandlers,
  ...providersHandlers,
  ...assistantsHandlers,
];
