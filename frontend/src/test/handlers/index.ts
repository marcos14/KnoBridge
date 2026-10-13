import { accountHandlers } from "./account";
import { adminHandlers } from "./admin";
import { apiKeysHandlers } from "./apiKeys";
import { auditHandlers } from "./audit";
import { authHandlers } from "./auth";
import { collectionsHandlers } from "./collections";
import { conversationsHandlers } from "./conversations";
import { dashboardHandlers } from "./dashboard";
import { harnessHandlers } from "./harness";
import { healthReadyOk } from "./health";
import { invitesHandlers } from "./invites";
import { knowledgeHandlers } from "./knowledge";
import { levelsHandlers } from "./levels";
import { membersHandlers } from "./members";
import { productsHandlers } from "./products";
import { providersHandlers } from "./providers";
import { recoveryHandlers } from "./recovery";
import { runnersHandlers } from "./runners";
import { setupHandlers } from "./setup";
import { sourcesHandlers } from "./sources";
import { ticketsHandlers } from "./tickets";
import { usageHandlers } from "./usage";
import { workspaceConversationsHandlers } from "./workspaceConversations";

export * from "./account";
export * from "./admin";
export * from "./apiKeys";
export * from "./audit";
export * from "./auth";
export * from "./collections";
export * from "./conversations";
export * from "./dashboard";
export * from "./errors";
export * from "./harness";
export * from "./health";
export * from "./invites";
export * from "./knowledge";
export * from "./levels";
export * from "./members";
export * from "./page";
export * from "./products";
export * from "./providers";
export * from "./record";
export * from "./recovery";
export * from "./runners";
export * from "./setup";
export * from "./sources";
export * from "./tickets";
export * from "./usage";
export * from "./workspaceConversations";

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
  ...productsHandlers,
  ...levelsHandlers,
  ...collectionsHandlers,
  ...runnersHandlers,
  ...apiKeysHandlers,
  ...sourcesHandlers,
  ...ticketsHandlers,
  ...harnessHandlers,
  ...knowledgeHandlers,
  ...conversationsHandlers,
  ...workspaceConversationsHandlers,
  ...dashboardHandlers,
  ...usageHandlers,
];
