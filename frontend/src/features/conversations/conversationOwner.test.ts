import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeWorkspaceConversation } from "@/test/factories";

import { conversationOwner } from "./conversationOwner";

const API_ROW = {
  channel: "api",
  user_id: null,
  user_name: null,
  user_email: null,
  api_key_id: "00000000-0000-4000-8000-0000000000a1",
  api_key_name: "ERP",
} as const;

describe("conversationOwner", () => {
  it("test_conversation_owner_of_a_member_is_name_and_email", () => {
    expect(conversationOwner(makeWorkspaceConversation(), i18n.t)).toEqual({
      name: "Ana Teste",
      detail: "ana@example.test",
    });
  });

  it("test_conversation_owner_of_the_api_is_the_key_name", () => {
    expect(conversationOwner(makeWorkspaceConversation(API_ROW), i18n.t)).toEqual({
      name: "API · ERP",
      detail: "Chave de API",
    });
  });

  it("test_conversation_owner_of_the_api_without_key_name", () => {
    const row = makeWorkspaceConversation({ ...API_ROW, api_key_name: null });

    expect(conversationOwner(row, i18n.t).name).toBe("API");
  });

  it("test_conversation_owner_of_a_member_without_names_is_empty", () => {
    const row = makeWorkspaceConversation({ user_name: null, user_email: null });

    expect(conversationOwner(row, i18n.t)).toEqual({ name: "", detail: "" });
  });
});
