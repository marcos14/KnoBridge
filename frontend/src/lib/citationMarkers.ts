/** Prefix of the internal href a `[n]` marker becomes; the Markdown view turns it into a button. */
export const CITATION_HREF_PREFIX = "#citation-";

/** Minimal mdast shapes this plugin touches (the full types are not a direct dependency). */
interface MdNode {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
}

const MARKER = /\[(\d+)\]/g;

/** Citation index of an href produced by `remarkCitationMarkers`, or `null` for any other link. */
export function citationIndexFromHref(href: string | undefined): number | null {
  if (href?.startsWith(CITATION_HREF_PREFIX) !== true) {
    return null;
  }
  const index = Number(href.slice(CITATION_HREF_PREFIX.length));
  return Number.isInteger(index) && index > 0 ? index : null;
}

/** Splits a text node at each `[n]` with `n` in `indexes`, turning the marker into a link node. */
function splitText(value: string, indexes: ReadonlySet<number>): MdNode[] {
  const nodes: MdNode[] = [];
  let last = 0;
  for (const match of value.matchAll(MARKER)) {
    const index = Number(match[1]);
    if (!indexes.has(index)) {
      continue;
    }
    if (match.index > last) {
      nodes.push({ type: "text", value: value.slice(last, match.index) });
    }
    nodes.push({
      type: "link",
      url: `${CITATION_HREF_PREFIX}${String(index)}`,
      children: [{ type: "text", value: match[0] }],
    });
    last = match.index + match[0].length;
  }
  if (last < value.length) {
    nodes.push({ type: "text", value: value.slice(last) });
  }
  return nodes;
}

function transform(node: MdNode, indexes: ReadonlySet<number>): void {
  if (node.children === undefined || node.type === "link" || node.type === "linkReference") {
    return;
  }
  const merged: MdNode[] = [];
  // The parser may split "[1]" into several text nodes (an unresolved reference); join them first.
  for (const child of node.children) {
    const previous = merged.at(-1);
    if (child.type === "text" && previous?.type === "text") {
      merged[merged.length - 1] = {
        type: "text",
        value: `${previous.value ?? ""}${child.value ?? ""}`,
      };
    } else {
      merged.push(child);
    }
  }
  node.children = merged.flatMap((child) => {
    if (child.type === "text") {
      return splitText(child.value ?? "", indexes);
    }
    transform(child, indexes);
    return [child];
  });
}

/**
 * Remark plugin: the `[n]` markers of an answer whose `n` is one of its citations become links to
 * `#citation-n`. Text inside code, links and other numbers in brackets stay as they are.
 */
export function remarkCitationMarkers(indexes: ReadonlySet<number>) {
  return () => (tree: MdNode) => {
    transform(tree, indexes);
  };
}

/** Whether a source URI can be opened as a web link (other URIs, such as file paths, are shown). */
export function isWebUri(uri: string): boolean {
  return /^https?:\/\//i.test(uri);
}
