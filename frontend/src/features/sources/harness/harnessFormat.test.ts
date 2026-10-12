import { describe, expect, it } from "vitest";

import {
  makeHarnessJob,
  makeHarnessModule,
  makeHarnessRejection,
  makeRunningHarnessJob,
} from "@/test/harnessFactories";

import {
  groupRejections,
  jobDuration,
  jobTokens,
  moduleMatches,
  rejectionSourceLocation,
  rejectionSources,
  shortCommit,
} from "./harnessFormat";

const NOW = new Date("2026-10-10T12:00:00Z");

describe("shortCommit", () => {
  it("test_short_commit_keeps_seven_characters", () => {
    expect(shortCommit("abcdef1234567")).toBe("abcdef1");
  });

  it("test_short_commit_keeps_null", () => {
    expect(shortCommit(null)).toBeNull();
  });
});

describe("jobDuration", () => {
  it("test_job_duration_prefers_the_reported_duration", () => {
    expect(jobDuration(makeHarnessJob(), NOW)).toBe("1 min 35 s");
  });

  it("test_job_duration_counts_until_now_while_running", () => {
    expect(jobDuration(makeRunningHarnessJob(), NOW)).toBe("2 min");
  });

  it("test_job_duration_uses_the_finish_without_a_reported_duration", () => {
    const job = makeHarnessJob({ duration_ms: null, finished_at: "2026-10-10T11:00:50Z" });

    expect(jobDuration(job, NOW)).toBe("45 s");
  });

  it("test_job_duration_is_undefined_before_the_start", () => {
    const job = makeHarnessJob({ duration_ms: null, started_at: null, status: "queued" });

    expect(jobDuration(job, NOW)).toBeUndefined();
  });
});

describe("jobTokens", () => {
  it("test_job_tokens_formats_input_and_output", () => {
    expect(jobTokens(makeHarnessJob(), "pt-BR")).toBe("12.000 / 3.400");
  });

  it("test_job_tokens_dash_when_unknown", () => {
    expect(jobTokens(makeRunningHarnessJob(), "pt-BR")).toBe("—");
    expect(jobTokens(makeHarnessJob({ output_tokens: null }), "pt-BR")).toBe("12.000 / —");
  });
});

describe("moduleMatches", () => {
  it("test_module_matches_title_key_or_pattern_ignoring_case", () => {
    const module = makeHarnessModule();

    expect(moduleMatches(module, "  ")).toBe(true);
    expect(moduleMatches(module, "FATURA")).toBe(true);
    expect(moduleMatches(module, "src-fat")).toBe(true);
    expect(moduleMatches(module, "/**")).toBe(true);
    expect(moduleMatches(module, "legado")).toBe(false);
  });
});

describe("rejection sources", () => {
  it("test_rejection_sources_read_fields_defensively", () => {
    const rejection = makeHarnessRejection({
      sources: [
        { path: "a.py", start_line: 3, end_line: 7, code: "bad_range" },
        { path: "", start_line: 1.5, end_line: "x", code: 4 },
        null,
      ],
    });

    expect(rejectionSources(rejection)).toEqual([
      { path: "a.py", startLine: 3, endLine: 7, code: "bad_range" },
      { path: null, startLine: null, endLine: null, code: null },
      { path: null, startLine: null, endLine: null, code: null },
    ]);
  });

  it("test_rejection_source_location_by_what_is_known", () => {
    const base = { path: "a.py", startLine: 3, endLine: 7, code: null };

    expect(rejectionSourceLocation(base)).toBe("a.py:3–7");
    expect(rejectionSourceLocation({ ...base, endLine: 3 })).toBe("a.py:3");
    expect(rejectionSourceLocation({ ...base, endLine: null })).toBe("a.py:3");
    expect(rejectionSourceLocation({ ...base, startLine: null })).toBe("a.py");
    expect(rejectionSourceLocation({ ...base, path: null })).toBeNull();
  });
});

describe("groupRejections", () => {
  it("test_group_rejections_counts_by_code_most_frequent_first", () => {
    const groups = groupRejections([
      makeHarnessRejection({ code: "symbol_mismatch", reason: "S" }),
      makeHarnessRejection({ code: "bad_range", reason: "B" }),
      makeHarnessRejection({ code: "symbol_mismatch", reason: "S" }),
      makeHarnessRejection({ code: "a_code", reason: "A" }),
    ]);

    expect(groups).toEqual([
      { code: "symbol_mismatch", reason: "S", count: 2 },
      { code: "a_code", reason: "A", count: 1 },
      { code: "bad_range", reason: "B", count: 1 },
    ]);
  });
});
