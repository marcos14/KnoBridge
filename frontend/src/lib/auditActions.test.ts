import { describe, expect, it } from "vitest";

import { AUDIT_ACTIONS, isAuditAction } from "./auditActions";

describe("auditActions", () => {
  it("test_audit_actions_lists_every_contract_action_once", () => {
    expect(AUDIT_ACTIONS).toHaveLength(63);
    expect(new Set(AUDIT_ACTIONS).size).toBe(AUDIT_ACTIONS.length);
    expect(AUDIT_ACTIONS).toContain("setup.completed");
    expect(AUDIT_ACTIONS).toContain("runner.revoked");
    expect(AUDIT_ACTIONS).toContain("harness_job.cancelled");
    expect(AUDIT_ACTIONS).toContain("harness_job.enqueued");
    expect(AUDIT_ACTIONS).toContain("harness_module.updated");
    expect(AUDIT_ACTIONS).toContain("knowledge_item.updated");
    expect(AUDIT_ACTIONS).toContain("superadmin.workspace_entered");
    expect(AUDIT_ACTIONS).toContain("superadmin.workspace_exited");
    expect(AUDIT_ACTIONS).toContain("api_key.revoked");
  });

  it("test_is_audit_action_accepts_only_known_codes", () => {
    expect(isAuditAction("auth.login.failed")).toBe(true);
    expect(isAuditAction("connector.synced")).toBe(false);
    expect(isAuditAction("toString")).toBe(false);
  });
});
