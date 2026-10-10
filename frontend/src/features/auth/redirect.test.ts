import { describe, expect, it } from "vitest";

import { loginPath, safeNextPath } from "./redirect";

describe("loginPath", () => {
  it("test_login_path_keeps_path_search_and_hash_as_next", () => {
    const path = loginPath({ pathname: "/w/abc/settings", search: "?tab=members", hash: "#top" });

    expect(path).toBe("/login?next=%2Fw%2Fabc%2Fsettings%3Ftab%3Dmembers%23top");
    expect(new URLSearchParams(path.split("?")[1]).get("next")).toBe(
      "/w/abc/settings?tab=members#top",
    );
  });
});

describe("safeNextPath", () => {
  it("test_safe_next_path_accepts_app_path", () => {
    expect(safeNextPath("/w/abc?tab=1")).toBe("/w/abc?tab=1");
  });

  it.each([null, "", "w/abc", "//evil.test", "/\\evil.test", "https://evil.test/"])(
    "test_safe_next_path_rejects_%j",
    (next) => {
      expect(safeNextPath(next)).toBe("/");
    },
  );
});
