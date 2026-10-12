import { describe, expect, it } from "vitest";

import { summarizeUserAgent } from "./userAgent";

describe("summarizeUserAgent", () => {
  it.each([
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
      "Chrome",
      "Windows",
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
      "Edge",
      "Windows",
    ],
    [
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 OPR/120.0.0.0",
      "Opera",
      "Linux",
    ],
    [
      "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:141.0) Gecko/20100101 Firefox/141.0",
      "Firefox",
      "Linux",
    ],
    [
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
      "Safari",
      "macOS",
    ],
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
      "Safari",
      "iOS",
    ],
    [
      "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
      "Chrome",
      "Android",
    ],
    [
      "Mozilla/5.0 (X11; CrOS x86_64 16181.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
      "Chrome",
      "ChromeOS",
    ],
  ])("test_summarize_user_agent_reads_browser_and_os (%#)", (userAgent, browser, os) => {
    expect(summarizeUserAgent(userAgent)).toEqual({ browser, os });
  });

  it("test_summarize_user_agent_unknown_header_has_null_fields", () => {
    expect(summarizeUserAgent("curl/8.9.1")).toEqual({ browser: null, os: null });
  });

  it("test_summarize_user_agent_without_header_has_null_fields", () => {
    expect(summarizeUserAgent(null)).toEqual({ browser: null, os: null });
  });
});
