import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { meQueryKey } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

export function isWorkspaceSuspendedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403 && error.code === "workspace_suspended";
}

/**
 * Becomes `true` when any query or mutation fails with 403 `workspace_suspended`: the workspace
 * was suspended after `me` was loaded. `me` is refetched so the switcher shows the new status.
 * Mount it once per workspace (keyed by id), so the flag does not leak to the next one.
 */
export function useWorkspaceSuspendedSignal(): boolean {
  const queryClient = useQueryClient();
  const [suspended, setSuspended] = useState(false);

  useEffect(() => {
    const onError = (error: unknown) => {
      if (isWorkspaceSuspendedError(error)) {
        setSuspended(true);
        void queryClient.invalidateQueries({ queryKey: meQueryKey });
      }
    };
    const unsubscribeQueries = queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "error") {
        onError(event.action.error);
      }
    });
    const unsubscribeMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "error") {
        onError(event.action.error);
      }
    });
    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
  }, [queryClient]);

  return suspended;
}
