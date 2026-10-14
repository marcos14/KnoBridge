/**
 * Allowed origins of a widget (`docs/specs/widget.md`, "Domínios permitidos e CORS"): what the
 * panel checks before saving, mirroring `backend/src/knobridge/widget/origins.py`. The server
 * stays the authority (its 422 `widget_origin_invalid` lists each origin and the reason); this
 * only spares a round trip and points at the line to fix.
 */

/** Why an origin is refused; the same `reason` values as the API. */
export type OriginProblem =
  | "malformed"
  | "scheme_not_allowed"
  | "path_not_allowed"
  | "wildcard_not_allowed"
  | "too_long"
  | "duplicate";

export const ORIGIN_PROBLEMS: readonly OriginProblem[] = [
  "malformed",
  "scheme_not_allowed",
  "path_not_allowed",
  "wildcard_not_allowed",
  "too_long",
  "duplicate",
];

/** Most origins a widget accepts. */
export const MAX_ALLOWED_ORIGINS = 50;
/** Longest origin accepted. */
export const ORIGIN_MAX_LENGTH = 255;

const DEFAULT_PORTS: Readonly<Record<string, string>> = { http: "80", https: "443" };
const LABEL = /^(?!-)[a-z0-9-]{1,63}(?<!-)$/;
const IPV6 = /^\[([0-9a-f:.]+)\](?::(\d*))?$/;
const HOST_AND_PORT = /^([^:[\]]+)(?::(\d*))?$/;

export interface OriginIssue {
  origin: string;
  reason: OriginProblem;
}

/** The origins typed one per line (commas also split), without blanks. */
export function splitOrigins(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

function hostProblem(host: string): OriginProblem | null {
  const labels = host.split(".");
  let named = labels;
  if (labels[0] === "*") {
    if (labels.length === 1 || labels.slice(1).includes("*")) {
      return "wildcard_not_allowed";
    }
    named = labels.slice(1);
  } else if (host.includes("*")) {
    return "wildcard_not_allowed";
  }
  return named.every((label) => LABEL.test(label)) ? null : "malformed";
}

function validPort(port: string | undefined): boolean {
  return port === undefined || port === "" || Number(port) <= 65535;
}

/**
 * The origin normalized (`https://a.com:443` → `https://a.com`, lower case), or why it is refused.
 */
export function normalizeOrigin(value: string): { origin: string } | { problem: OriginProblem } {
  if (value.length > ORIGIN_MAX_LENGTH) {
    return { problem: "too_long" };
  }
  if (value.trim() === "*") {
    return { problem: "wildcard_not_allowed" };
  }
  if (!value.includes("://") || /\s/.test(value)) {
    return { problem: "malformed" };
  }
  const lowered = value.toLowerCase();
  const [scheme = "", rest = ""] = lowered.split("://", 2);
  const defaultPort = DEFAULT_PORTS[scheme];
  if (defaultPort === undefined) {
    return { problem: "scheme_not_allowed" };
  }
  if (/[/?#]/.test(rest)) {
    return { problem: "path_not_allowed" };
  }
  if (rest.includes("@")) {
    return { problem: "malformed" };
  }
  const ipv6 = IPV6.exec(rest);
  const named = ipv6 === null ? HOST_AND_PORT.exec(rest) : null;
  const host = ipv6?.[1] === undefined ? named?.[1] : `[${ipv6[1]}]`;
  const port = ipv6 === null ? named?.[2] : ipv6[2];
  if (host === undefined || !validPort(port)) {
    return { problem: "malformed" };
  }
  if (ipv6 === null) {
    const problem = hostProblem(host);
    if (problem !== null) {
      return { problem };
    }
  }
  const kept = port === undefined || port === "" || port === defaultPort ? "" : `:${port}`;
  return { origin: `${scheme}://${host}${kept}` };
}

/** Every refused origin of the list, in order (a repeated one after its first is `duplicate`). */
export function originIssues(origins: readonly string[]): OriginIssue[] {
  const seen = new Set<string>();
  const issues: OriginIssue[] = [];
  for (const origin of origins) {
    const result = normalizeOrigin(origin);
    if ("problem" in result) {
      issues.push({ origin, reason: result.problem });
    } else if (seen.has(result.origin)) {
      issues.push({ origin, reason: "duplicate" });
    } else {
      seen.add(result.origin);
    }
  }
  return issues;
}

/**
 * The issues of a 422 `widget_origin_invalid` (`details.origins`), keeping only well-formed items
 * with a known reason; anything else in `details` is ignored.
 */
export function originIssuesFromDetails(details: unknown): OriginIssue[] {
  if (typeof details !== "object" || details === null || !("origins" in details)) {
    return [];
  }
  const { origins } = details;
  if (!Array.isArray(origins)) {
    return [];
  }
  return origins.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }
    const origin: unknown = "origin" in item ? item.origin : undefined;
    const reason: unknown = "reason" in item ? item.reason : undefined;
    const known = ORIGIN_PROBLEMS.find((problem) => problem === reason);
    return typeof origin === "string" && known !== undefined ? [{ origin, reason: known }] : [];
  });
}
