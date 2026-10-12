import { Navigate, Outlet } from "react-router";

import { useSetupStatus } from "@/lib/api/setup";

import { GuardError, GuardLoading } from "./GuardStatus";
import { SETUP_PATH } from "./redirect";

/** Sends every route to `/setup` while the instance has no user yet. */
export function RequireSetupDone() {
  const status = useSetupStatus();

  if (status.isPending) {
    return <GuardLoading />;
  }
  if (status.isError) {
    return <GuardError onRetry={() => void status.refetch()} />;
  }
  if (status.data.needs_setup) {
    return <Navigate to={SETUP_PATH} replace />;
  }
  return <Outlet />;
}
