import { http } from "msw";

import type { AuditEvent } from "@/lib/api/audit";

import { makeAuditEvents } from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const WORKSPACE_AUDIT = "*/v1/workspaces/:workspaceId/audit";
const INSTANCE_AUDIT = "*/v1/admin/audit";

type AuditScope = "workspace" | "instance";

function pathOf(scope: AuditScope): string {
  return scope === "workspace" ? WORKSPACE_AUDIT : INSTANCE_AUDIT;
}

/** GET of the workspace or instance audit listing `events` (paged, filters ignored). */
export function auditAs(scope: AuditScope, events: AuditEvent[] = makeAuditEvents()) {
  return http.get(pathOf(scope), ({ request }) => page(request, events));
}

/**
 * Audit listing that keeps the query string of each request, so a test can assert which filters
 * and page the screen asked for. `queries` holds one `URLSearchParams` per request, in order.
 */
export function auditRecorder(scope: AuditScope, events: AuditEvent[] = makeAuditEvents()) {
  const queries: URLSearchParams[] = [];
  const handler = http.get(pathOf(scope), ({ request }) => {
    queries.push(new URL(request.url).searchParams);
    return page(request, events);
  });
  return { handler, queries };
}

/** GET of the workspace or instance audit failing on the server (500). */
export function auditServerError(scope: AuditScope) {
  return http.get(pathOf(scope), () => apiErrorResponse(500, "internal_error"));
}

export const workspaceAuditOk = auditAs("workspace");
export const instanceAuditOk = auditAs("instance");

export const auditHandlers = [workspaceAuditOk, instanceAuditOk];
