import type { Citation } from "@/lib/api/conversations";
import { formatDate } from "@/lib/intl";

/** Characters of a commit SHA shown to people, like `git log --oneline`. */
export const SHORT_SHA_LENGTH = 7;

/**
 * Where a citation points (`docs/specs/chat-sse.md`, v0.3 fields; a commit's author and ISO date
 * since v0.4, `null` before), as the interface shows it.
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
  | { type: "legacy" };

function present(value: string | null | undefined): string | null {
  return value === undefined || value === null || value === "" ? null : value;
}

/** Line range of a cited chunk: `L10–L20`, `L10` for one line, `null` without lines. */
export function citationLines(citation: Citation): string | null {
  const start = citation.start_line ?? null;
  if (start === null) {
    return null;
  }
  const end = citation.end_line ?? null;
  return end === null || end === start ? `L${String(start)}` : `L${String(start)}–L${String(end)}`;
}

/**
 * What the citation points to: a commit (with its SHA), a file (path, lines, symbol, language) or,
 * for answers saved before the location fields existed, `legacy` (shown by title, excerpt and URI).
 */
export function citationSource(citation: Citation): CitationSource {
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
 * One-line location for the list of sources: `path:L10–L20`, the path alone, `commit abc1234`, or
 * `null` for a legacy citation.
 */
export function citationLocation(citation: Citation): string | null {
  const source = citationSource(citation);
  switch (source.type) {
    case "commit":
      return `commit ${source.shortSha}`;
    case "file":
      return source.lines === null ? source.path : `${source.path}:${source.lines}`;
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
