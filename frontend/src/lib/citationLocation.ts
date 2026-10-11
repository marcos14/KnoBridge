import type { Citation } from "@/lib/api/conversations";
import { formatDate } from "@/lib/intl";

/** Characters of a commit SHA shown to people, like `git log --oneline`. */
export const SHORT_SHA_LENGTH = 7;

/** Trust seal of a knowledge item (`revisado` once approved in review). */
export type KnowledgeSeal = "inferido" | "revisado";

/** Where a knowledge item was verified in the code, as the interface shows it. */
export interface EvidenceLocation {
  path: string;
  /** `L80–L92`, `L80`, or `null` without lines. */
  lines: string | null;
  /** `path:L80–L92`, or the path alone without lines. */
  location: string;
  symbol: string | null;
  excerpt: string | null;
}

/**
 * Where a citation points (`docs/specs/chat-sse.md`, v0.3 fields; a commit's author and ISO date
 * since v0.4, `null` before; a knowledge item with its seal and evidence since v0.5), as the
 * interface shows it.
 */
export type CitationSource =
  | { type: "commit"; sha: string; shortSha: string; author: string | null; date: string | null }
  | {
      type: "file";
      path: string;
      lines: string | null;
      symbol: string | null;
      language: string | null;
    }
  | {
      type: "knowledge";
      /** Key of the item, from `knowledge:<key>`; `null` when the URI does not carry it. */
      key: string | null;
      confidence: KnowledgeSeal | null;
      evidence: EvidenceLocation[];
    }
  | { type: "legacy" };

const KNOWLEDGE_URI_PREFIX = "knowledge:";

function present(value: string | null | undefined): string | null {
  return value === undefined || value === null || value === "" ? null : value;
}

/** A line range: `L10–L20`, `L10` for one line, `null` without a start. */
export function lineRange(start: number | null, end: number | null): string | null {
  if (start === null) {
    return null;
  }
  return end === null || end === start ? `L${String(start)}` : `L${String(start)}–L${String(end)}`;
}

/** Line range of a cited chunk: `L10–L20`, `L10` for one line, `null` without lines. */
export function citationLines(citation: Citation): string | null {
  return lineRange(citation.start_line ?? null, citation.end_line ?? null);
}

/** One piece of evidence of a knowledge item (citation or review), located for people. */
export function evidenceLocation(evidence: {
  path: string;
  start_line: number | null;
  end_line: number | null;
  symbol?: string | null;
  excerpt?: string | null;
}): EvidenceLocation {
  const lines = lineRange(evidence.start_line, evidence.end_line);
  return {
    path: evidence.path,
    lines,
    location: lines === null ? evidence.path : `${evidence.path}:${lines}`,
    symbol: present(evidence.symbol),
    excerpt: present(evidence.excerpt),
  };
}

function knowledgeSeal(value: string | null | undefined): KnowledgeSeal | null {
  return value === "inferido" || value === "revisado" ? value : null;
}

function knowledgeKey(uri: string | null): string | null {
  return uri?.startsWith(KNOWLEDGE_URI_PREFIX) === true
    ? present(uri.slice(KNOWLEDGE_URI_PREFIX.length))
    : null;
}

/**
 * What the citation points to: a knowledge item (seal and evidence), a commit (with its SHA), a
 * file (path, lines, symbol, language) or, for answers saved before the location fields existed,
 * `legacy` (shown by title, excerpt and URI).
 */
export function citationSource(citation: Citation): CitationSource {
  if (citation.kind === "knowledge") {
    return {
      type: "knowledge",
      key: knowledgeKey(citation.uri),
      confidence: knowledgeSeal(citation.confidence),
      evidence: (citation.evidence ?? []).map(evidenceLocation),
    };
  }
  const sha = present(citation.sha);
  if (citation.kind === "commit" && sha !== null) {
    return {
      type: "commit",
      sha,
      shortSha: sha.slice(0, SHORT_SHA_LENGTH),
      author: present(citation.author),
      date: present(citation.date),
    };
  }
  const path = present(citation.path);
  if (path !== null) {
    return {
      type: "file",
      path,
      lines: citationLines(citation),
      symbol: present(citation.symbol),
      language: present(citation.language),
    };
  }
  return { type: "legacy" };
}

/**
 * One-line location for the list of sources: `path:L10–L20`, the path alone, `commit abc1234`,
 * the first evidence of a knowledge item (`path:L80–L92 +2` with more), or `null` for a legacy
 * citation or a knowledge item without evidence.
 */
export function citationLocation(citation: Citation): string | null {
  const source = citationSource(citation);
  switch (source.type) {
    case "commit":
      return `commit ${source.shortSha}`;
    case "file":
      return source.lines === null ? source.path : `${source.path}:${source.lines}`;
    case "knowledge": {
      const [first, ...rest] = source.evidence;
      if (first === undefined) {
        return null;
      }
      return rest.length === 0 ? first.location : `${first.location} +${String(rest.length)}`;
    }
    case "legacy":
      return null;
  }
}

/**
 * Who wrote a cited commit and when, as "Ana Souza · 1 de out. de 2026" (either part alone when
 * the other is missing), or `null` when neither is known. A date the browser cannot parse is shown
 * as it came. `timeZone` defaults to the browser's; tests pin it.
 */
export function commitAuthorship(
  author: string | null,
  date: string | null,
  locale: string,
  timeZone?: string,
): string | null {
  const parsed = date === null ? null : new Date(date);
  const shownDate =
    parsed === null || Number.isNaN(parsed.getTime()) ? date : formatDate(parsed, locale, timeZone);
  const parts = [author, shownDate].filter((part): part is string => part !== null);
  return parts.length === 0 ? null : parts.join(" · ");
}
