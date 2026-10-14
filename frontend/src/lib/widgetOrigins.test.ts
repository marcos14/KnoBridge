import { describe, expect, it } from "vitest";

import {
  normalizeOrigin,
  originIssues,
  originIssuesFromDetails,
  splitOrigins,
} from "./widgetOrigins";

describe("splitOrigins", () => {
  it("test_split_origins_takes_lines_and_commas_without_blanks", () => {
    expect(splitOrigins(" https://a.com \n\n,https://b.com, \n")).toEqual([
      "https://a.com",
      "https://b.com",
    ]);
  });
});

describe("normalizeOrigin", () => {
  it.each([
    ["https://App.Cliente.com.br", "https://app.cliente.com.br"],
    ["https://a.com:443", "https://a.com"],
    ["http://a.com:80", "http://a.com"],
    ["http://intranet.local:8080", "http://intranet.local:8080"],
    ["https://*.cliente.com.br", "https://*.cliente.com.br"],
    ["http://[::1]:3000", "http://[::1]:3000"],
    ["http://[::1]", "http://[::1]"],
    ["http://a.com:", "http://a.com"],
  ])("test_normalize_origin_accepts_%s", (value, origin) => {
    expect(normalizeOrigin(value)).toEqual({ origin });
  });

  it.each([
    [`https://${"a".repeat(250)}.com`, "too_long"],
    ["*", "wildcard_not_allowed"],
    ["https://*", "wildcard_not_allowed"],
    ["https://*.*.a.com", "wildcard_not_allowed"],
    ["https://a.*.com", "wildcard_not_allowed"],
    ["a.com", "malformed"],
    ["https://a .com", "malformed"],
    ["ftp://a.com", "scheme_not_allowed"],
    ["https://a.com/", "path_not_allowed"],
    ["https://a.com/app", "path_not_allowed"],
    ["https://a.com?x=1", "path_not_allowed"],
    ["https://a.com#top", "path_not_allowed"],
    ["https://user@a.com", "malformed"],
    ["https://a.com:99999", "malformed"],
    ["https://-a.com", "malformed"],
    ["https://", "malformed"],
    ["https://[zz]", "malformed"],
  ])("test_normalize_origin_refuses_%s", (value, problem) => {
    expect(normalizeOrigin(value)).toEqual({ problem });
  });
});

describe("originIssues", () => {
  it("test_origin_issues_lists_bad_and_repeated_origins_in_order", () => {
    expect(originIssues(["https://a.com", "a.com", "https://A.com:443"])).toEqual([
      { origin: "a.com", reason: "malformed" },
      { origin: "https://A.com:443", reason: "duplicate" },
    ]);
  });

  it("test_origin_issues_is_empty_for_good_origins", () => {
    expect(originIssues(["https://a.com", "https://b.com"])).toEqual([]);
  });
});

describe("originIssuesFromDetails", () => {
  it("test_origin_issues_from_details_reads_the_api_details", () => {
    expect(
      originIssuesFromDetails({
        origins: [
          { origin: "https://a.com/x", reason: "path_not_allowed" },
          { origin: "https://b.com", reason: "unknown_reason" },
          { origin: 3, reason: "malformed" },
          null,
          "text",
          {},
        ],
      }),
    ).toEqual([{ origin: "https://a.com/x", reason: "path_not_allowed" }]);
  });

  it.each([null, "x", {}, { origins: "x" }])(
    "test_origin_issues_from_details_ignores_%s",
    (details) => {
      expect(originIssuesFromDetails(details)).toEqual([]);
    },
  );
});
