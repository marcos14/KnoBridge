import { describe, expect, it } from "vitest";

import { isHttpUrl, parseInline, parseMarkdown } from "./markdown.ts";

const CITES = new Set([1, 2]);

describe("parseInline", () => {
  it("test_parse_inline_reads_code_bold_italic_and_links", () => {
    const nodes = parseInline(
      "Use `npm` **com _cuidado_** e *calma* em [docs](https://x.com/a).",
      CITES,
    );

    expect(nodes).toEqual([
      { type: "text", text: "Use " },
      { type: "code", text: "npm" },
      { type: "text", text: " " },
      {
        type: "strong",
        children: [
          { type: "text", text: "com " },
          { type: "em", children: [{ type: "text", text: "cuidado" }] },
        ],
      },
      { type: "text", text: " e " },
      { type: "em", children: [{ type: "text", text: "calma" }] },
      { type: "text", text: " em " },
      { type: "link", href: "https://x.com/a", text: "docs" },
      { type: "text", text: "." },
    ]);
  });

  it("test_parse_inline_turns_known_markers_into_citations", () => {
    expect(parseInline("Feche o caixa [1][3].", CITES)).toEqual([
      { type: "text", text: "Feche o caixa " },
      { type: "cite", index: 1 },
      { type: "text", text: "[3]." },
    ]);
  });

  it("test_parse_inline_keeps_unsafe_links_and_snake_case_as_text", () => {
    expect(parseInline("[x](javascript:alert(1)) fecha_caixa_dia", CITES)).toEqual([
      { type: "text", text: "[x](javascript:alert(1)) fecha_caixa_dia" },
    ]);
  });
});

describe("parseMarkdown", () => {
  it("test_parse_markdown_splits_paragraphs_and_line_breaks", () => {
    expect(parseMarkdown("a\nb\r\n\r\nc", CITES)).toEqual([
      {
        type: "paragraph",
        children: [{ type: "text", text: "a" }, { type: "break" }, { type: "text", text: "b" }],
      },
      { type: "paragraph", children: [{ type: "text", text: "c" }] },
    ]);
  });

  it("test_parse_markdown_reads_lists_and_switches_list_type", () => {
    const blocks = parseMarkdown("Passos:\n- um\n* dois\n1. três\n2) quatro\nfim", CITES);

    expect(blocks.map((block) => block.type)).toEqual(["paragraph", "list", "list", "paragraph"]);
    expect(blocks[1]).toEqual({
      type: "list",
      ordered: false,
      items: [[{ type: "text", text: "um" }], [{ type: "text", text: "dois" }]],
    });
    expect(blocks[2]).toMatchObject({ type: "list", ordered: true });
  });

  it("test_parse_markdown_reads_headings_and_code_fences", () => {
    expect(parseMarkdown("## Título\n```sql\nselect *\n\nfrom t\n```\ndepois", CITES)).toEqual([
      { type: "heading", children: [{ type: "text", text: "Título" }] },
      { type: "code", text: "select *\n\nfrom t" },
      { type: "paragraph", children: [{ type: "text", text: "depois" }] },
    ]);
  });

  it("test_parse_markdown_keeps_an_unclosed_fence_as_code", () => {
    expect(parseMarkdown("antes\n```\nparcial", CITES)).toEqual([
      { type: "paragraph", children: [{ type: "text", text: "antes" }] },
      { type: "code", text: "parcial" },
    ]);
  });

  it("test_parse_markdown_of_empty_text_has_no_blocks", () => {
    expect(parseMarkdown("", CITES)).toEqual([]);
  });
});

describe("isHttpUrl", () => {
  it("test_is_http_url_accepts_only_http_and_https", () => {
    expect(isHttpUrl("https://a.com/x")).toBe(true);
    expect(isHttpUrl("http://a.com")).toBe(true);
    expect(isHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isHttpUrl("manual/caixa.md")).toBe(false);
    expect(isHttpUrl(null)).toBe(false);
    expect(isHttpUrl(undefined)).toBe(false);
  });
});
