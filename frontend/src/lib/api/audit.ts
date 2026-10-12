import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiClient, unwrap } from "./client";
import type { components } from "./schema.gen";

export type AuditEvent = components["schemas"]["AuditEventOut"];
export type AuditAction = components["schemas"]["AuditAction"];

/** Filters of an audit listing, as the API takes them; the period is `[occurredFrom, occurredTo)`. */
export interface AuditQuery {
  action?: AuditAction;
  actorUserId?: string;
  /** ISO 8601 instants. */
  occurredFrom?: string;
  occurredTo?: string;
  limit: number;
  offset: number;
}

function toParams({ action, actorUserId, occurredFrom, occurredTo, limit, offset }: AuditQuery) {
  return {
    action,
    actor_user_id: actorUserId,
    occurred_from: occurredFrom,
    occurred_to: occurredTo,
    limit,
    offset,
  };
}

export function workspaceAuditQueryKey(workspaceId: string) {
  return ["api", "workspaces", workspaceId, "audit"] as const;
}

export const instanceAuditQueryKey = ["api", "admin", "audit"] as const;

/** One page of the workspace's audit trail, newest first (owner or admin). */
export function useWorkspaceAudit(workspaceId: string, query: AuditQuery) {
  return useQuery({
    queryKey: [...workspaceAuditQueryKey(workspaceId), query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/audit", {
          params: { path: { workspace_id: workspaceId }, query: toParams(query) },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** One page of the instance events (setup, logins, superadmin work), newest first. */
export function useInstanceAudit(query: AuditQuery) {
  return useQuery({
    queryKey: [...instanceAuditQueryKey, query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/admin/audit", { params: { query: toParams(query) }, signal }),
      ),
    placeholderData: keepPreviousData,
  });
}
