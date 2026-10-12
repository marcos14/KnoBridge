import { Navigate, Outlet } from "react-router";

import { useSetupStatus } from "@/lib/api/setup";

import { GuardError, GuardLoading } from "./GuardStatus";

/** Keeps `/setup` reachable only while the instance has no user; afterwards it goes to `/`. */
export function RequireSetupPending() {
  const status = useSetupStatus();

  if (status.isPending) {
    return <GuardLoading />;
  }
  if (status.isError) {
    return <GuardError onRetry={() => void status.refetch()} />;
  }
  if (!status.data.needs_setup) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
