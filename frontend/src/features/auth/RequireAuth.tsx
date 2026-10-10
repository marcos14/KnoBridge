import { Navigate, Outlet, useLocation } from "react-router";

import { useLoggedOutByUser, useMe } from "@/lib/api/auth";

import { GuardError, GuardLoading } from "./GuardStatus";
import { LOGIN_PATH, loginPath } from "./redirect";

/**
 * Lets only logged-in users through; anonymous ones go to the login, keeping the destination,
 * except right after an explicit logout (plain `/login`).
 */
export function RequireAuth() {
  const me = useMe();
  const loggedOutByUser = useLoggedOutByUser();
  const location = useLocation();

  if (me.isPending) {
    return <GuardLoading />;
  }
  if (me.isError) {
    return <GuardError onRetry={() => void me.refetch()} />;
  }
  if (me.data === null) {
    // After an explicit logout, a plain login: someone else may log in next on this browser.
    return <Navigate to={loggedOutByUser ? LOGIN_PATH : loginPath(location)} replace />;
  }
  return <Outlet />;
}
