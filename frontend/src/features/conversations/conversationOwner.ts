import type { TFunction } from "i18next";

import type { WorkspaceConversation } from "@/lib/api/workspaceConversations";

type OwnerFields = Pick<
  WorkspaceConversation,
  "channel" | "user_name" | "user_email" | "api_key_name" | "widget_name" | "visitor"
>;

/** Who owns a conversation, as the admin view shows it: a name, a secondary line and who asks. */
export interface ConversationOwner {
  name: string;
  detail: string;
  /** Who asked the questions ("Pergunta de …"). */
  asker: string;
}

/**
 * The visitor of a widget conversation: name and e-mail of the signed identity (whichever it
 * has), the external id when it has neither, or "Visitante anônimo" without an identity.
 */
export function visitorLabel(visitor: WorkspaceConversation["visitor"], t: TFunction): string {
  if (visitor === null) {
    return t("conversations.anonymousVisitor");
  }
  const { name, email, external_id: externalId } = visitor;
  if (name !== null && email !== null) {
    return t("conversations.visitorNameEmail", { name, email });
  }
  const known = name ?? email;
  return known === null
    ? t("conversations.visitorExternal", { id: externalId })
    : t("conversations.visitorKnown", { who: known });
}

/**
 * A member's conversation shows the member's name and e-mail; one of the public API or of MCP has
 * no user and shows "API · <key>" or "MCP · <key>" (the name stays after the key is revoked); one
 * of a widget shows "Widget · <widget>" and the visitor.
 */
export function conversationOwner(row: OwnerFields, t: TFunction): ConversationOwner {
  if (row.channel === "api" || row.channel === "mcp") {
    const name =
      row.api_key_name === null
        ? t(`conversations.${row.channel}OwnerUnnamed`)
        : t(`conversations.${row.channel}Owner`, { key: row.api_key_name });
    return { name, detail: t("conversations.apiOwnerHint"), asker: name };
  }
  if (row.channel === "widget") {
    return {
      name:
        row.widget_name === null
          ? t("conversations.widgetOwnerUnnamed")
          : t("conversations.widgetOwner", { widget: row.widget_name }),
      detail: visitorLabel(row.visitor, t),
      asker: row.visitor?.name ?? row.visitor?.email ?? t("conversations.visitor"),
    };
  }
  const name = row.user_name ?? "";
  return { name, detail: row.user_email ?? "", asker: name };
}
