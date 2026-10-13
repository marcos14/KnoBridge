import type { ProviderKind } from "./api/providers";

/**
 * Chat models suggested for a credential of each kind: the ones with a price in the backend's
 * table (`backend/src/knobridge/llm/chat_pricing.py`), so the level shows its estimated cost.
 * Suggestions only: any model id of the provider is accepted.
 */
const CHAT_MODELS: Record<ProviderKind, readonly string[]> = {
  openai: ["gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano", "gpt-4o-mini", "gpt-4o"],
  anthropic: ["claude-sonnet-5-5", "claude-haiku-4-5", "claude-opus-5-5"],
  openrouter: [
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-haiku-4.5",
  ],
  // The fake provider (development and tests) answers with any model id and has no price.
  fake: ["fake-chat"],
};

/** Models offered for a credential of `kind`; none without a credential. */
export function chatModelSuggestions(kind: ProviderKind | undefined): readonly string[] {
  return kind === undefined ? [] : CHAT_MODELS[kind];
}
