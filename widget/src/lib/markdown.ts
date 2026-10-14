// Safe Markdown subset of the answers (docs/specs/widget.md, "Comportamento"): paragraphs, lists,
// bold, italic, inline and block code, http(s) links and the [n] citation markers. It produces a
// tree, never HTML: the element renders it with Lit templates, which escape every text.

export type Inline =
  | { type: "text"; text: string }
  | { type: "break" }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "code"; text: string }
  | { type: "link"; href: string; text: string }
  | { type: "cite"; index: number };

export type Block =
  | { type: "paragraph"; children: Inline[] }
  | { type: "heading"; children: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "code"; text: string };

/** The known citation indexes (a Set, or the Map of titles by index). */
export interface CitationIndexes {
  has(index: number): boolean;
}

const INLINE =
  /`([^`\n]+)`|\*\*(.+?)\*\*|\*([^*\s][^*\n]*?)\*|(?<!\w)_([^_\n]+)_(?!\w)|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|\[(\d{1,3})\]/g;

/** Parses one line of inline Markdown; `[n]` becomes a citation only when `n` is a known index. */
export function parseInline(text: string, citations: CitationIndexes): Inline[] {
  const out: Inline[] = [];
  const pushText = (value: string) => {
    if (!value) return;
    const last = out.at(-1);
    if (last?.type === "text") last.text += value;
    else out.push({ type: "text", text: value });
  };
  let cursor = 0;
  for (const match of text.matchAll(INLINE)) {
    pushText(text.slice(cursor, match.index));
    cursor = match.index + match[0].length;
    const [whole, code, strong, star, underscore, linkText, href, cite] = match;
    const emphasis = star ?? underscore;
    if (code !== undefined) out.push({ type: "code", text: code });
    else if (strong !== undefined)
      out.push({ type: "strong", children: parseInline(strong, citations) });
    else if (emphasis !== undefined)
      out.push({ type: "em", children: parseInline(emphasis, citations) });
    else if (href !== undefined) out.push({ type: "link", href, text: String(linkText) });
    else if (citations.has(Number(cite))) out.push({ type: "cite", index: Number(cite) });
    else pushText(whole);
  }
  pushText(text.slice(cursor));
  return out;
}

const UNORDERED = /^\s*[-*+]\s+/;
const ORDERED = /^\s*\d{1,9}[.)]\s+/;
const HEADING = /^#{1,6}\s+/;
const FENCE = /^\s*```/;

export function parseMarkdown(source: string, citations: CitationIndexes): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: Inline[][] } | null = null;
  let fence: string[] | null = null;

  const flush = () => {
    if (paragraph.length) {
      const children: Inline[] = [];
      paragraph.forEach((line, i) => {
        if (i > 0) children.push({ type: "break" });
        children.push(...parseInline(line, citations));
      });
      blocks.push({ type: "paragraph", children });
      paragraph = [];
    }
    if (list) {
      blocks.push({ type: "list", ...list });
      list = null;
    }
  };

  for (const line of source.replace(/\r\n/g, "\n").split("\n")) {
    if (fence) {
      if (FENCE.test(line)) {
        blocks.push({ type: "code", text: fence.join("\n") });
        fence = null;
      } else fence.push(line);
      continue;
    }
    if (FENCE.test(line)) {
      flush();
      fence = [];
    } else if (!line.trim()) {
      flush();
    } else if (HEADING.test(line)) {
      flush();
      blocks.push({ type: "heading", children: parseInline(line.replace(HEADING, ""), citations) });
    } else if (UNORDERED.test(line) || ORDERED.test(line)) {
      const ordered = !UNORDERED.test(line);
      if (paragraph.length || (list && list.ordered !== ordered)) flush();
      list ??= { ordered, items: [] };
      list.items.push(parseInline(line.replace(ordered ? ORDERED : UNORDERED, ""), citations));
    } else {
      if (list) flush();
      paragraph.push(line);
    }
  }
  // An unclosed fence (a stream still arriving, for instance) keeps what came after it as code.
  if (fence) blocks.push({ type: "code", text: fence.join("\n") });
  flush();
  return blocks;
}

/** Only http(s) URLs become links or "Abrir" buttons; anything else stays text. */
export function isHttpUrl(value: string | null | undefined): value is string {
  if (!value) return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
