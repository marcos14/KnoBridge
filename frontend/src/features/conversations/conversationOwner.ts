import type { TFunction } from "i18next";

import type { WorkspaceConversation } from "@/lib/api/workspaceConversations";

type OwnerFields = Pick<
  WorkspaceConversation,
  "channel" | "user_name" | "user_email" | "api_key_name"
>;

/** Who owns a conversation, as the admin view shows it: a name and a secondary line. */
export interface ConversationOwner {
  name: string;
  detail: string;
}

/**
 * A member's conversation shows the member's name and e-mail; one of the public API has no user
 * and shows "API · <key name>" instead (the name stays after the key is revoked).
 */
export function conversationOwner(row: OwnerFields, t: TFunction): ConversationOwner {
  if (row.channel === "api") {
    return {
      name:
        row.api_key_name === null
          ? t("conversations.apiOwnerUnnamed")
          : t("conversations.apiOwner", { key: row.api_key_name }),
      detail: t("conversations.apiOwnerHint"),
    };
  }
  return { name: row.user_name ?? "", detail: row.user_email ?? "" };
}
