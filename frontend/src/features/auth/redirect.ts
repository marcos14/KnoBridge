export const LOGIN_PATH = "/login";
export const SETUP_PATH = "/setup";

/** Query parameter that carries where to go after logging in. */
export const NEXT_PARAM = "next";

interface LocationLike {
  pathname: string;
  search: string;
  hash: string;
}

/** Login URL that brings the user back to `location` afterwards. */
export function loginPath(location: LocationLike): string {
  const next = `${location.pathname}${location.search}${location.hash}`;
  return `${LOGIN_PATH}?${new URLSearchParams({ [NEXT_PARAM]: next }).toString()}`;
}

/**
 * Validates a `next` value before navigating to it: only paths inside the app are accepted, so a
 * crafted link cannot send the user to another site after login ("//evil.test", "https://...").
 */
export function safeNextPath(next: string | null): string {
  if (next?.startsWith("/") !== true || next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  return next;
}
