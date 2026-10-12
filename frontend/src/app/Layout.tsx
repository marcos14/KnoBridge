import { Outlet } from "react-router";

import { SessionExpiryHandler } from "@/features/auth/SessionExpiryHandler";

/** Root route: reacts to expired sessions everywhere; the frame comes from the child layouts. */
export function Layout() {
  return (
    <>
      <SessionExpiryHandler />
      <Outlet />
    </>
  );
}
