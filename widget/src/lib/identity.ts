// The `sub` of a signed identity `v1.<base64url payload>.<hex signature>` (docs/specs/widget.md,
// "Identidade assinada"), read only to tell visitors apart in the browser pointer. The widget never
// checks the signature nor holds the kbs_ secret: the server verifies the identity it receives.

/**
 * Stands for an identity that cannot be read. It never matches a stored pointer (one is saved only
 * after the server accepts the identity, and the server refuses this one), so a visitor with a
 * broken identity never sees an anonymous conversation kept in the same browser.
 */
export const UNREADABLE_SUB = "\u0000unreadable";

const SUB_MAX_LENGTH = 200;

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "="));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

/** `null` without identity; the `sub` claim; or UNREADABLE_SUB when it is out of the format. */
export function identitySub(identity: string | null | undefined): string | null {
  if (!identity) return null;
  const parts = identity.split(".");
  if (parts.length !== 3 || parts[0] !== "v1" || !parts[1]) return UNREADABLE_SUB;
  try {
    const claims = JSON.parse(decodeBase64Url(parts[1])) as { sub?: unknown } | null;
    const sub = claims?.sub;
    if (typeof sub === "string" && sub.length > 0 && sub.length <= SUB_MAX_LENGTH) return sub;
  } catch {
    // Not base64url, not UTF-8 or not JSON: the server will refuse it as `malformed`.
  }
  return UNREADABLE_SUB;
}
