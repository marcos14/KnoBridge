/**
 * Filters of the audit screens, kept in the URL query string so a filtered view can be shared:
 * `?action=<code>&actor=<user id>&from=YYYY-MM-DD&to=YYYY-MM-DD&offset=<n>`.
 */

import type { AuditAction, AuditQuery } from "@/lib/api/audit";
import { isAuditAction } from "@/lib/auditActions";

export interface AuditFilters {
  action?: AuditAction;
  actor?: string;
  /** First day of the period, inclusive (`YYYY-MM-DD`, local calendar). */
  from?: string;
  /** Last day of the period, inclusive. */
  to?: string;
}

export interface AuditSearch {
  filters: AuditFilters;
  offset: number;
}

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Parts of a real calendar day written as `YYYY-MM-DD`, or `undefined`. */
function dayParts(value: string): [number, number, number] | undefined {
  const match = DAY.exec(value);
  if (match === null) {
    return undefined;
  }
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(year, month - 1, day);
  if (date.getMonth() !== month - 1 || date.getDate() !== day) {
    return undefined;
  }
  return [year, month, day];
}

function validDay(value: string | null): string | undefined {
  return value !== null && dayParts(value) !== undefined ? value : undefined;
}

/**
 * Filters and offset read from the URL. Values the API would refuse (unknown action, malformed
 * id or day, negative offset) are dropped, so a hand-edited link still opens a listing.
 */
export function parseAuditSearch(params: URLSearchParams): AuditSearch {
  const action = params.get("action");
  const actor = params.get("actor");
  const offset = Number(params.get("offset") ?? "0");
  return {
    filters: {
      action: action !== null && isAuditAction(action) ? action : undefined,
      actor: actor !== null && UUID.test(actor) ? actor : undefined,
      from: validDay(params.get("from")),
      to: validDay(params.get("to")),
    },
    offset: Number.isInteger(offset) && offset > 0 ? offset : 0,
  };
}

/** Query string of a filtered page; empty filters and the first page leave no trace. */
export function auditSearchParams({ filters, offset }: AuditSearch): URLSearchParams {
  const params = new URLSearchParams();
  const entries: [string, string | undefined][] = [
    ["action", filters.action],
    ["actor", filters.actor],
    ["from", filters.from],
    ["to", filters.to],
  ];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== "") {
      params.set(key, value);
    }
  }
  if (offset > 0) {
    params.set("offset", String(offset));
  }
  return params;
}

/** Start of the local day `day` (`YYYY-MM-DD`) plus `shift` days, as an ISO instant. */
function dayStart(day: string, shift = 0): string | undefined {
  const parts = dayParts(day);
  if (parts === undefined) {
    return undefined;
  }
  const [year, month, date] = parts;
  return new Date(year, month - 1, date + shift).toISOString();
}

/**
 * Query sent to the API for the filters: the inclusive day range becomes the half-open interval
 * `[start of "from", start of the day after "to")` of the browser's time zone.
 */
export function toAuditQuery({ filters, offset }: AuditSearch, limit: number): AuditQuery {
  return {
    action: filters.action,
    actorUserId: filters.actor,
    occurredFrom: filters.from === undefined ? undefined : dayStart(filters.from),
    occurredTo: filters.to === undefined ? undefined : dayStart(filters.to, 1),
    limit,
    offset,
  };
}

/** Whether any filter is set (shows the "clear filters" button). */
export function hasAuditFilters(filters: AuditFilters): boolean {
  return Object.values(filters).some((value) => value !== undefined);
}

/** A value of `details` written for reading: text as is, everything else as indented JSON. */
export function formatDetailValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}
