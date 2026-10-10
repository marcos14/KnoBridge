import { Navigate, Outlet, useLocation } from "react-router";

import { useMe } from "@/lib/api/auth";

import { GuardError, GuardLoading } from "./GuardStatus";
import { loginPath } from "./redirect";

/** Lets only logged-in users through; anonymous ones go to the login, keeping the destination. */
export function RequireAuth() {
  const me = useMe();
  const location = useLocation();

  if (me.isPending) {
    return <GuardLoading />;
  }
  if (me.isError) {
    return <GuardError onRetry={() => void me.refetch()} />;
  }
  if (me.data === null) {
    return <Navigate to={loginPath(location)} replace />;
  }
  return <Outlet />;
}
