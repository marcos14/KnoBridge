import { describe, expect, it } from "vitest";

import type { Citation } from "@/lib/api/conversations";
import { makeCitation } from "@/test/factories";
import { makeKnowledgeCitation } from "@/test/knowledgeFactories";

import {
  citationLines,
  citationLocation,
  citationSource,
  commitAuthorship,
  evidenceLocation,
} from "./citationLocation";

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
      author: null,
      date: null,
    });
  });

  it("test_citation_source_reads_the_commit_author_and_date", () => {
    const citation = makeCitation({
      kind: "commit",
      sha: SHA,
      author: "Ana Souza",
      date: "2026-10-01T15:00:00+00:00",
    });

    expect(citationSource(citation)).toMatchObject({
      author: "Ana Souza",
      date: "2026-10-01T15:00:00+00:00",
    });
  });

  it("test_citation_source_is_legacy_without_location_fields", () => {
    expect(citationSource(makeCitation())).toEqual({ type: "legacy" });
    expect(citationSource(makeCitation({ kind: "commit", sha: null }))).toEqual({
      type: "legacy",
    });
  });
});

describe("citationSource for knowledge", () => {
  it("test_citation_source_reads_a_knowledge_item_with_seal_and_evidence", () => {
    expect(citationSource(makeKnowledgeCitation())).toEqual({
      type: "knowledge",
      key: "src-faturamento.R001",
      confidence: "revisado",
      evidence: [
        {
          path: "src/faturamento/notas.ts",
          lines: "L80–L92",
          location: "src/faturamento/notas.ts:L80–L92",
          symbol: "emitirNota",
          excerpt: "if (!cliente.cnpj) {",
        },
        {
          path: "src/faturamento/cliente.ts",
          lines: "L12",
          location: "src/faturamento/cliente.ts:L12",
          symbol: null,
          excerpt: null,
        },
      ],
    });
  });

  it("test_citation_source_tolerates_a_knowledge_citation_without_v05_fields", () => {
    expect(
      citationSource(
        makeKnowledgeCitation({ uri: "outro:x", confidence: "talvez", evidence: undefined }),
      ),
    ).toEqual({ type: "knowledge", key: null, confidence: null, evidence: [] });
    expect(
      citationSource(makeKnowledgeCitation({ uri: null, confidence: null, evidence: null })),
    ).toMatchObject({ key: null, confidence: null, evidence: [] });
  });
});

describe("evidenceLocation", () => {
  it("test_evidence_location_without_lines_is_the_path", () => {
    expect(
      evidenceLocation({ path: "docs/a.md", start_line: null, end_line: null, symbol: "" }),
    ).toEqual({
      path: "docs/a.md",
      lines: null,
      location: "docs/a.md",
      symbol: null,
      excerpt: null,
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

  it("test_citation_location_of_knowledge_is_the_first_evidence", () => {
    const citation = makeKnowledgeCitation();

    expect(citationLocation(citation)).toBe("src/faturamento/notas.ts:L80–L92 +1");
    expect(citationLocation({ ...citation, evidence: citation.evidence?.slice(0, 1) })).toBe(
      "src/faturamento/notas.ts:L80–L92",
    );
    expect(citationLocation({ ...citation, evidence: [] })).toBeNull();
  });
});

describe("commitAuthorship", () => {
  const DATE = "2026-10-01T15:00:00+00:00";

  it("test_commit_authorship_joins_author_and_date", () => {
    expect(commitAuthorship("Ana Souza", DATE, "pt-BR", "UTC")).toBe(
      "Ana Souza · 1 de out. de 2026",
    );
  });

  it("test_commit_authorship_shows_the_part_it_has", () => {
    expect(commitAuthorship("Ana Souza", null, "pt-BR", "UTC")).toBe("Ana Souza");
    expect(commitAuthorship(null, DATE, "pt-BR", "UTC")).toBe("1 de out. de 2026");
  });

  it("test_commit_authorship_keeps_an_unparsable_date_as_it_came", () => {
    expect(commitAuthorship("Ana", "ontem", "pt-BR")).toBe("Ana · ontem");
  });

  it("test_commit_authorship_is_null_without_author_and_date", () => {
    expect(commitAuthorship(null, null, "pt-BR")).toBeNull();
  });
});
