/**
 * Filters of the audit screens, kept in the URL query string so a filtered view can be shared:
 * `?action=<code>&actor=<user id>&from=YYYY-MM-DD&to=YYYY-MM-DD&offset=<n>`.
 */

import type { AuditAction, AuditQuery } from "@/lib/api/audit";
import { isAuditAction } from "@/lib/auditActions";
import { dayPeriod, validDay } from "@/lib/days";
import { parseOffset } from "@/lib/pagination";
import { isUuid } from "@/lib/uuid";

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

/**
 * Filters and offset read from the URL. Values the API would refuse (unknown action, malformed
 * id or day, negative offset) are dropped, so a hand-edited link still opens a listing.
 */
export function parseAuditSearch(params: URLSearchParams): AuditSearch {
  const action = params.get("action");
  const actor = params.get("actor");
  return {
    filters: {
      action: action !== null && isAuditAction(action) ? action : undefined,
      actor: isUuid(actor) ? actor : undefined,
      from: validDay(params.get("from")),
      to: validDay(params.get("to")),
    },
    offset: parseOffset(params.get("offset")),
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

/**
 * Query sent to the API for the filters: the inclusive day range becomes the half-open interval
 * `[start of "from", start of the day after "to")` of the browser's time zone.
 */
export function toAuditQuery({ filters, offset }: AuditSearch, limit: number): AuditQuery {
  const period = dayPeriod(filters.from, filters.to);
  return {
    action: filters.action,
    actorUserId: filters.actor,
    occurredFrom: period.start,
    occurredTo: period.end,
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
