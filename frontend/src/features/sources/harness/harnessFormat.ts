import type { HarnessJob, HarnessModule, HarnessRejection } from "@/lib/api/harness";

import { formatCount, formatDuration } from "../format";

/** Length of a short commit SHA, as in the citations. */
const SHORT_SHA_LENGTH = 7;

/** The first seven characters of a commit SHA; `null` stays `null`. */
export function shortCommit(sha: string | null): string | null {
  return sha === null ? null : sha.slice(0, SHORT_SHA_LENGTH);
}

/**
 * How long the job took (`duration_ms` reported by the runner), or has been running until `now`;
 * `undefined` before it starts or when it ended without starting.
 */
export function jobDuration(job: HarnessJob, now: Date): string | undefined {
  if (job.duration_ms !== null) {
    return formatDuration(job.duration_ms);
  }
  if (job.started_at === null) {
    return undefined;
  }
  const end = job.finished_at === null ? now : new Date(job.finished_at);
  return formatDuration(end.getTime() - new Date(job.started_at).getTime());
}

/** Input / output tokens ("12.000 / 3.400"); "—" while the runner has not reported them. */
export function jobTokens(job: HarnessJob, locale: string): string {
  if (job.input_tokens === null && job.output_tokens === null) {
    return "—";
  }
  return [job.input_tokens, job.output_tokens]
    .map((value) => (value === null ? "—" : formatCount(value, locale)))
    .join(" / ");
}

/** Whether a module's title, key or one of its patterns contains `filter` (ignoring case). */
export function moduleMatches(module: HarnessModule, filter: string): boolean {
  const needle = filter.trim().toLowerCase();
  if (needle === "") {
    return true;
  }
  return [module.title, module.key, ...module.paths].some((text) =>
    text.toLowerCase().includes(needle),
  );
}

/** One source cited by a rejected item, as the runner sent it (`RunnerRejectionSource`). */
interface RejectionSource {
  path: string | null;
  startLine: number | null;
  endLine: number | null;
  code: string | null;
}

function field(value: unknown, key: string): unknown {
  return typeof value === "object" && value !== null && key in value
    ? (value as Record<string, unknown>)[key]
    : undefined;
}

function integer(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/**
 * The cited sources of a rejection. The contract types them loosely (`unknown[]`), so each one is
 * read defensively: a missing or malformed field becomes `null`.
 */
export function rejectionSources(rejection: HarnessRejection): RejectionSource[] {
  return rejection.sources.map((source) => ({
    path: text(field(source, "path")),
    startLine: integer(field(source, "start_line")),
    endLine: integer(field(source, "end_line")),
    code: text(field(source, "code")),
  }));
}

/** Where a cited source points: `path:10–20`, `path:10`, `path`, or `null` without a path. */
export function rejectionSourceLocation(source: RejectionSource): string | null {
  if (source.path === null) {
    return null;
  }
  if (source.startLine === null) {
    return source.path;
  }
  const end =
    source.endLine === null || source.endLine === source.startLine
      ? ""
      : `–${String(source.endLine)}`;
  return `${source.path}:${String(source.startLine)}${end}`;
}

export interface RejectionGroup {
  code: string;
  /** The fixed pt-BR reason the runner wrote for this code. */
  reason: string;
  count: number;
}

/** Rejections grouped by code, the most frequent first (ties by code), with the reason text. */
export function groupRejections(rejections: readonly HarnessRejection[]): RejectionGroup[] {
  const groups = new Map<string, RejectionGroup>();
  for (const rejection of rejections) {
    const group = groups.get(rejection.code);
    if (group === undefined) {
      groups.set(rejection.code, { code: rejection.code, reason: rejection.reason, count: 1 });
    } else {
      group.count += 1;
    }
  }
  return [...groups.values()].sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));
}
