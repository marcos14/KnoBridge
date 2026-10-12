import { describe, expect, it } from "vitest";

import { makeInvitationPreview, makeMe } from "@/test/factories";

import { invitationStep, sameEmail } from "./invitationStep";

const invitee = makeMe({ user: { ...makeMe().user, email: "BRUNO@example.test" } });

describe("invitationStep", () => {
  it("test_invitation_step_signup_for_anonymous_new_address", () => {
    expect(invitationStep(makeInvitationPreview(), null)).toBe("signup");
  });

  it("test_invitation_step_login_for_anonymous_existing_account", () => {
    expect(invitationStep(makeInvitationPreview({ user_exists: true }), null)).toBe("login");
  });

  it("test_invitation_step_accept_for_invited_account_ignoring_case", () => {
    expect(invitationStep(makeInvitationPreview({ user_exists: true }), invitee)).toBe("accept");
  });

  it("test_invitation_step_mismatch_for_other_account", () => {
    expect(invitationStep(makeInvitationPreview(), makeMe())).toBe("mismatch");
  });

  it("test_same_email_compares_case_insensitively", () => {
    expect(sameEmail("Ana@Example.test", "ana@example.TEST")).toBe(true);
    expect(sameEmail("ana@example.test", "bruno@example.test")).toBe(false);
  });
});
