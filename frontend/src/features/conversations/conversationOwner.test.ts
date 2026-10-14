import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { makeWorkspaceConversation } from "@/test/factories";

import { conversationOwner, visitorLabel } from "./conversationOwner";

const API_ROW = {
  channel: "api",
  user_id: null,
  user_name: null,
  user_email: null,
  api_key_id: "00000000-0000-4000-8000-0000000000a1",
  api_key_name: "ERP",
} as const;

const WIDGET_ROW = {
  channel: "widget",
  user_id: null,
  user_name: null,
  user_email: null,
  widget_id: "00000000-0000-4000-8000-0000000000b1",
  widget_name: "Site público",
} as const;

const VISITOR = { name: "Ana Souza", email: "ana@exemplo.com.br", external_id: "cliente-42" };

describe("conversationOwner", () => {
  it("test_conversation_owner_of_a_member_is_name_and_email", () => {
    expect(conversationOwner(makeWorkspaceConversation(), i18n.t)).toEqual({
      name: "Ana Teste",
      detail: "ana@example.test",
      asker: "Ana Teste",
    });
  });

  it("test_conversation_owner_of_the_api_is_the_key_name", () => {
    expect(conversationOwner(makeWorkspaceConversation(API_ROW), i18n.t)).toEqual({
      name: "API · ERP",
      detail: "Chave de API",
      asker: "API · ERP",
    });
  });

  it("test_conversation_owner_of_the_api_without_key_name", () => {
    const row = makeWorkspaceConversation({ ...API_ROW, api_key_name: null });

    expect(conversationOwner(row, i18n.t).name).toBe("API");
  });

  it("test_conversation_owner_of_mcp_is_the_key_name", () => {
    const row = makeWorkspaceConversation({ ...API_ROW, channel: "mcp" });

    expect(conversationOwner(row, i18n.t)).toEqual({
      name: "MCP · ERP",
      detail: "Chave de API",
      asker: "MCP · ERP",
    });
    expect(conversationOwner({ ...row, api_key_name: null }, i18n.t).name).toBe("MCP");
  });

  it("test_conversation_owner_of_a_widget_with_a_signed_visitor", () => {
    const row = makeWorkspaceConversation({ ...WIDGET_ROW, visitor: VISITOR });

    expect(conversationOwner(row, i18n.t)).toEqual({
      name: "Widget · Site público",
      detail: "Visitante: Ana Souza (ana@exemplo.com.br)",
      asker: "Ana Souza",
    });
  });

  it("test_conversation_owner_of_a_widget_with_an_anonymous_visitor", () => {
    const row = makeWorkspaceConversation({ ...WIDGET_ROW, widget_name: null, visitor: null });

    expect(conversationOwner(row, i18n.t)).toEqual({
      name: "Widget",
      detail: "Visitante anônimo",
      asker: "Visitante",
    });
  });

  it("test_conversation_owner_of_a_widget_asker_falls_back_to_the_email", () => {
    const row = makeWorkspaceConversation({ ...WIDGET_ROW, visitor: { ...VISITOR, name: null } });

    expect(conversationOwner(row, i18n.t).asker).toBe("ana@exemplo.com.br");
  });

  it("test_conversation_owner_of_a_member_without_names_is_empty", () => {
    const row = makeWorkspaceConversation({ user_name: null, user_email: null });

    expect(conversationOwner(row, i18n.t)).toEqual({ name: "", detail: "", asker: "" });
  });
});

describe("visitorLabel", () => {
  it.each([
    [{ ...VISITOR, email: null }, "Visitante: Ana Souza"],
    [{ ...VISITOR, name: null }, "Visitante: ana@exemplo.com.br"],
    [{ ...VISITOR, name: null, email: null }, "Visitante identificado (cliente-42)"],
  ])("test_visitor_label_shows_what_the_identity_has_%#", (visitor, label) => {
    expect(visitorLabel(visitor, i18n.t)).toBe(label);
  });
});
