import { Outlet } from "react-router";

import { useMe } from "@/lib/api/auth";

import { ForbiddenPage } from "./ForbiddenPage";

/** Lets only instance superadmins through. Must sit under `RequireAuth`. */
export function RequireSuperadmin() {
  const { data: me } = useMe();

  if (me?.is_superadmin !== true) {
    return <ForbiddenPage />;
  }
  return <Outlet />;
}
