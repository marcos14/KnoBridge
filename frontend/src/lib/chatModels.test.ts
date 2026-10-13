import { describe, expect, it } from "vitest";

import { chatModelSuggestions } from "./chatModels";

describe("chatModelSuggestions", () => {
  it("test_chat_model_suggestions_follow_the_credential_kind", () => {
    expect(chatModelSuggestions("openai")[0]).toBe("gpt-4.1-mini");
    expect(chatModelSuggestions("anthropic")).toContain("claude-haiku-4-5");
    expect(chatModelSuggestions("openrouter")).toContain("openai/gpt-4.1-mini");
    expect(chatModelSuggestions("fake")).toEqual(["fake-chat"]);
  });

  it("test_chat_model_suggestions_are_empty_without_a_credential", () => {
    expect(chatModelSuggestions(undefined)).toEqual([]);
  });
});
