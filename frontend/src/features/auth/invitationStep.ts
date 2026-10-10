import type { Me } from "@/lib/api/auth";
import type { InvitationPreview } from "@/lib/api/invites";

/**
 * What the invitation screen offers:
 * - `signup`: nobody logged in and no account for the address; create one and join.
 * - `login`: nobody logged in, but the address has an account; log in with it first.
 * - `accept`: logged in with the invited address; one click joins.
 * - `mismatch`: logged in with another address; log out to continue.
 */
export type InvitationStep = "signup" | "login" | "accept" | "mismatch";

/** Same address, ignoring case (the backend compares e-mails case-insensitively). */
export function sameEmail(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

export function invitationStep(preview: InvitationPreview, me: Me | null): InvitationStep {
  if (me !== null) {
    return sameEmail(me.user.email, preview.email) ? "accept" : "mismatch";
  }
  return preview.user_exists ? "login" : "signup";
}
