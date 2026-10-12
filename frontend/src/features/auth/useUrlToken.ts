import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

/** Query parameter of the links sent by e-mail (reset, verification, invitation). */
export const TOKEN_PARAM = "token";

/**
 * Token of an e-mailed link (`?token=`). It is read once and then removed from the address bar
 * (navigation with `replace`), so it does not stay in the history nor leak to whoever looks at the
 * screen. Returns `undefined` when the link had no token.
 */
export function useUrlToken(): string | undefined {
  const location = useLocation();
  const navigate = useNavigate();
  const urlToken = new URLSearchParams(location.search).get(TOKEN_PARAM);
  const [token] = useState(() => (urlToken === null || urlToken === "" ? undefined : urlToken));

  useEffect(() => {
    if (urlToken === null) {
      return;
    }
    const rest = new URLSearchParams(location.search);
    rest.delete(TOKEN_PARAM);
    const search = rest.toString();
    void navigate(
      {
        pathname: location.pathname,
        search: search === "" ? "" : `?${search}`,
        hash: location.hash,
      },
      { replace: true },
    );
  }, [urlToken, location.pathname, location.search, location.hash, navigate]);

  return token;
}
