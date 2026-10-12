import { describe, expect, it } from "vitest";

import {
  auditSearchParams,
  formatDetailValue,
  hasAuditFilters,
  parseAuditSearch,
  toAuditQuery,
} from "./auditFilters";

const ACTOR = "00000000-0000-4000-8000-000000000101";

describe("parseAuditSearch", () => {
  it("test_parse_audit_search_reads_every_filter_and_offset", () => {
    const params = new URLSearchParams(
      `action=auth.login.failed&actor=${ACTOR}&from=2026-10-01&to=2026-10-09&offset=40`,
    );

    expect(parseAuditSearch(params)).toEqual({
      filters: { action: "auth.login.failed", actor: ACTOR, from: "2026-10-01", to: "2026-10-09" },
      offset: 40,
    });
  });

  it("test_parse_audit_search_defaults_to_no_filters_and_first_page", () => {
    expect(parseAuditSearch(new URLSearchParams())).toEqual({
      filters: { action: undefined, actor: undefined, from: undefined, to: undefined },
      offset: 0,
    });
  });

  it("test_parse_audit_search_drops_values_the_api_would_refuse", () => {
    const params = new URLSearchParams(
      "action=toString&actor=not-a-uuid&from=2026-02-30&to=10/09/2026&offset=-20",
    );

    expect(parseAuditSearch(params)).toEqual({
      filters: { action: undefined, actor: undefined, from: undefined, to: undefined },
      offset: 0,
    });
  });

  it("test_parse_audit_search_ignores_fractional_offset", () => {
    expect(parseAuditSearch(new URLSearchParams("offset=2.5")).offset).toBe(0);
  });
});

describe("auditSearchParams", () => {
  it("test_audit_search_params_writes_only_what_is_set", () => {
    const params = auditSearchParams({
      filters: { action: "user.created", actor: undefined, from: "2026-10-01" },
      offset: 20,
    });

    expect(params.toString()).toBe("action=user.created&from=2026-10-01&offset=20");
  });

  it("test_audit_search_params_is_empty_for_first_unfiltered_page", () => {
    expect(auditSearchParams({ filters: { to: "" }, offset: 0 }).toString()).toBe("");
  });

  it("test_audit_search_params_round_trips_through_parse", () => {
    const search = {
      filters: { action: "membership.removed" as const, actor: ACTOR, from: "2026-01-01" },
      offset: 60,
    };

    expect(parseAuditSearch(auditSearchParams(search))).toEqual({
      filters: { ...search.filters, to: undefined },
      offset: 60,
    });
  });
});

describe("toAuditQuery", () => {
  it("test_to_audit_query_turns_inclusive_days_into_half_open_period", () => {
    const query = toAuditQuery(
      {
        filters: { action: "user.created", actor: ACTOR, from: "2026-10-01", to: "2026-10-31" },
        offset: 20,
      },
      20,
    );

    expect(query).toEqual({
      action: "user.created",
      actorUserId: ACTOR,
      occurredFrom: new Date(2026, 9, 1).toISOString(),
      occurredTo: new Date(2026, 10, 1).toISOString(),
      limit: 20,
      offset: 20,
    });
  });

  it("test_to_audit_query_without_filters_sends_only_the_page", () => {
    expect(toAuditQuery({ filters: {}, offset: 0 }, 50)).toEqual({
      action: undefined,
      actorUserId: undefined,
      occurredFrom: undefined,
      occurredTo: undefined,
      limit: 50,
      offset: 0,
    });
  });

  it("test_to_audit_query_drops_malformed_days", () => {
    const query = toAuditQuery({ filters: { from: "ontem", to: "2026-13-01" }, offset: 0 }, 20);

    expect(query.occurredFrom).toBeUndefined();
    expect(query.occurredTo).toBeUndefined();
  });
});

describe("hasAuditFilters", () => {
  it("test_has_audit_filters_detects_any_set_filter", () => {
    expect(hasAuditFilters({})).toBe(false);
    expect(hasAuditFilters({ action: undefined, to: undefined })).toBe(false);
    expect(hasAuditFilters({ to: "2026-10-01" })).toBe(true);
  });
});

describe("formatDetailValue", () => {
  it("test_format_detail_value_keeps_text_and_indents_the_rest", () => {
    expect(formatDetailValue("editor")).toBe("editor");
    expect(formatDetailValue(3)).toBe("3");
    expect(formatDetailValue(null)).toBe("null");
    expect(formatDetailValue({ a: [1] })).toBe('{\n  "a": [\n    1\n  ]\n}');
  });
});
