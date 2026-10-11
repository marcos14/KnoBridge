import { describe, expect, it } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";

import { citationLines, citationLocation, citationSource } from "./citationLocation";

const SHA = "0123456789abcdef0123456789abcdef01234567";

describe("citationLines", () => {
  it("test_citation_lines_formats_a_range", () => {
    expect(citationLines(makeCitation({ start_line: 10, end_line: 20 }))).toBe("L10–L20");
  });

  it("test_citation_lines_formats_one_line", () => {
    expect(citationLines(makeCitation({ start_line: 7, end_line: 7 }))).toBe("L7");
    expect(citationLines(makeCitation({ start_line: 7, end_line: null }))).toBe("L7");
  });

  it("test_citation_lines_is_null_without_lines", () => {
    expect(citationLines(makeCitation())).toBeNull();
    expect(citationLines(makeCitation({ start_line: null, end_line: 3 }))).toBeNull();
  });
});

describe("citationSource", () => {
  it("test_citation_source_reads_a_code_chunk", () => {
    const citation = makeCitation({
      kind: "file",
      path: "src/caixa.ts",
      start_line: 3,
      end_line: 9,
      symbol: "fecharCaixa",
      language: "typescript",
    });

    expect(citationSource(citation)).toEqual({
      type: "file",
      path: "src/caixa.ts",
      lines: "L3–L9",
      symbol: "fecharCaixa",
      language: "typescript",
    });
  });

  it("test_citation_source_reads_a_document_without_lines", () => {
    const citation = makeCitation({ kind: "file", path: "manual.pdf", symbol: "", language: null });

    expect(citationSource(citation)).toEqual({
      type: "file",
      path: "manual.pdf",
      lines: null,
      symbol: null,
      language: null,
    });
  });

  it("test_citation_source_reads_a_commit", () => {
    expect(citationSource(makeCitation({ kind: "commit", sha: SHA }))).toEqual({
      type: "commit",
      sha: SHA,
      shortSha: "0123456",
    });
  });

  it("test_citation_source_is_legacy_without_location_fields", () => {
    expect(citationSource(makeCitation())).toEqual({ type: "legacy" });
    expect(citationSource(makeCitation({ kind: "commit", sha: null }))).toEqual({
      type: "legacy",
    });
  });
});

describe("citationLocation", () => {
  it.each<[Partial<Citation>, string | null]>([
    [{ kind: "file", path: "src/a.py", start_line: 1, end_line: 4 }, "src/a.py:L1–L4"],
    [{ kind: "file", path: "manual.pdf" }, "manual.pdf"],
    [{ kind: "commit", sha: SHA }, "commit 0123456"],
    [{}, null],
  ])("test_citation_location_formats_%o", (overrides, expected) => {
    expect(citationLocation(makeCitation(overrides))).toBe(expected);
  });
});
