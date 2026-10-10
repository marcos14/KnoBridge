import { describe, expect, it } from "vitest";

import { citationIndexFromHref, remarkCitationMarkers } from "./citationMarkers";

interface Node {
  type: string;
  value?: string;
  url?: string;
  children?: Node[];
}

function run(tree: Node, indexes: number[]) {
  remarkCitationMarkers(new Set(indexes))()(tree);
  return tree;
}

const text = (value: string): Node => ({ type: "text", value });

describe("remarkCitationMarkers", () => {
  it("test_citation_markers_become_links_for_known_indexes", () => {
    const tree = run(
      { type: "root", children: [{ type: "paragraph", children: [text("Veja [1] e [3].")] }] },
      [1],
    );

    expect(tree.children?.[0]?.children).toEqual([
      text("Veja "),
      { type: "link", url: "#citation-1", children: [text("[1]")] },
      text(" e [3]."),
    ]);
  });

  it("test_citation_markers_join_split_text_nodes_first", () => {
    const tree = run({ type: "paragraph", children: [text("Fim ["), text("2"), text("]")] }, [2]);

    expect(tree.children).toEqual([
      text("Fim "),
      { type: "link", url: "#citation-2", children: [text("[2]")] },
    ]);
  });

  it("test_citation_markers_leave_code_and_links_alone", () => {
    const code = { type: "inlineCode", value: "[1]" };
    const link = { type: "link", url: "https://x.test", children: [text("[1]")] };
    const tree = run(
      { type: "paragraph", children: [code, link, { type: "emphasis", children: [text("[1]")] }] },
      [1],
    );

    expect(tree.children?.[0]).toEqual(code);
    expect(tree.children?.[1]).toEqual(link);
    expect(tree.children?.[2]?.children?.[0]).toMatchObject({ type: "link", url: "#citation-1" });
  });

  it("test_citation_markers_keep_text_without_markers", () => {
    const tree = run({ type: "paragraph", children: [{ type: "text" }] }, [1]);

    expect(tree.children).toEqual([]);
  });

  it("test_citation_index_from_href", () => {
    expect(citationIndexFromHref("#citation-4")).toBe(4);
    expect(citationIndexFromHref("#citation-0")).toBeNull();
    expect(citationIndexFromHref("#citation-x")).toBeNull();
    expect(citationIndexFromHref("https://x.test")).toBeNull();
    expect(citationIndexFromHref(undefined)).toBeNull();
  });
});
