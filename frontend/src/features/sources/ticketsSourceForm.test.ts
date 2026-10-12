import { describe, expect, it } from "vitest";

import { TICKETS_FORM_DEFAULTS, ticketsConfig, ticketsFieldsFromConfig } from "./ticketsSourceForm";

describe("ticketsFieldsFromConfig", () => {
  it("test_tickets_fields_keep_the_defaults_without_config", () => {
    expect(ticketsFieldsFromConfig({})).toEqual(TICKETS_FORM_DEFAULTS);
    expect(ticketsFieldsFromConfig({ path: "/sources/x" })).toEqual({
      includeInternalNotes: false,
      anonymize: true,
      statuses: ["open", "pending", "resolved", "closed"],
    });
  });

  it("test_tickets_fields_read_the_stored_config_and_drop_unknown_statuses", () => {
    expect(
      ticketsFieldsFromConfig({
        include_internal_notes: true,
        anonymize: false,
        statuses: ["closed", "archived", "resolved"],
      }),
    ).toEqual({ includeInternalNotes: true, anonymize: false, statuses: ["resolved", "closed"] });
  });
});

describe("ticketsConfig", () => {
  it("test_tickets_config_sends_the_statuses_in_canonical_order", () => {
    expect(
      ticketsConfig({ includeInternalNotes: true, anonymize: true, statuses: ["closed", "open"] }),
    ).toEqual({ include_internal_notes: true, anonymize: true, statuses: ["open", "closed"] });
  });
});
