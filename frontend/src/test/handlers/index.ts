import { authHandlers } from "./auth";
import { healthReadyOk } from "./health";
import { invitesHandlers } from "./invites";
import { recoveryHandlers } from "./recovery";
import { setupHandlers } from "./setup";

export * from "./auth";
export * from "./errors";
export * from "./health";
export * from "./invites";
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
];
