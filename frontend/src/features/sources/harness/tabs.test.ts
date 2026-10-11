import { describe, expect, it } from "vitest";

import { parseRunnerSourceTab } from "./tabs";

describe("parseRunnerSourceTab", () => {
  it("test_parse_runner_source_tab_reads_a_known_tab", () => {
    expect(parseRunnerSourceTab("jobs")).toBe("jobs");
  });

  it("test_parse_runner_source_tab_falls_back_to_modules", () => {
    expect(parseRunnerSourceTab(null)).toBe("modules");
    expect(parseRunnerSourceTab("knowledge-x")).toBe("modules");
  });
});
