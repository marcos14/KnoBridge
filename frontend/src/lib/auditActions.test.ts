import { describe, expect, it } from "vitest";

import { AUDIT_ACTIONS, isAuditAction } from "./auditActions";

describe("auditActions", () => {
  it("test_audit_actions_lists_every_contract_action_once", () => {
    expect(AUDIT_ACTIONS).toHaveLength(43);
    expect(new Set(AUDIT_ACTIONS).size).toBe(AUDIT_ACTIONS.length);
    expect(AUDIT_ACTIONS).toContain("setup.completed");
  });

  it("test_is_audit_action_accepts_only_known_codes", () => {
    expect(isAuditAction("auth.login.failed")).toBe(true);
    expect(isAuditAction("connector.synced")).toBe(false);
    expect(isAuditAction("toString")).toBe(false);
  });
});
