import { describe, expect, it } from "vitest";

import { CARD_STATUSES, cardsConfig, cardsFieldsFromConfig } from "./cardsSourceForm";

describe("cardsFieldsFromConfig", () => {
  it("test_cards_fields_from_config_reads_a_stored_config", () => {
    expect(
      cardsFieldsFromConfig({ include_comments: false, statuses: ["done", "backlog", "x"] }),
    ).toEqual({ includeComments: false, cardStatuses: ["backlog", "done"] });
  });

  it("test_cards_fields_from_config_keeps_the_defaults_when_missing", () => {
    expect(cardsFieldsFromConfig({ path: "/sources/x" })).toEqual({
      includeComments: true,
      cardStatuses: [...CARD_STATUSES],
    });
  });
});

describe("cardsConfig", () => {
  it("test_cards_config_orders_the_statuses", () => {
    expect(
      cardsConfig({
        anonymize: false,
        includeComments: true,
        cardStatuses: ["cancelled", "in_progress"],
      }),
    ).toEqual({ anonymize: false, include_comments: true, statuses: ["in_progress", "cancelled"] });
  });
});
