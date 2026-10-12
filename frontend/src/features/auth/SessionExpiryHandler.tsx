import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";

import { meQueryKey } from "@/lib/api/auth";
import { setUnauthorizedHandler } from "@/lib/api/client";

import { LOGIN_PATH, loginPath } from "./redirect";

/**
 * Reacts to an unexpected 401 from any API call (session expired or revoked): marks the user as
 * anonymous in the `useMe` cache and goes to the login, keeping the current page as destination.
 * Rendered once, inside the router, by the app layout.
 */
export function SessionExpiryHandler() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  // The handler outlives renders; the ref gives it the location at the moment the 401 arrives.
  const locationRef = useRef(location);

  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      queryClient.setQueryData(meQueryKey, null);
      const current = locationRef.current;
      if (current.pathname !== LOGIN_PATH) {
        void navigate(loginPath(current), { replace: true });
      }
    });
    return () => {
      setUnauthorizedHandler(null);
    };
  }, [queryClient, navigate]);

  return null;
}
