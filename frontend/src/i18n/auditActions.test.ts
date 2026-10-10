import { describe, expect, it } from "vitest";

import { AUDIT_ACTIONS } from "@/lib/auditActions";

import { auditActionLabel } from "./auditActions";
import { i18n } from "./index";

const t = i18n.t.bind(i18n);

describe("auditActionLabel", () => {
  it("test_audit_action_label_translates_known_action", () => {
    expect(auditActionLabel("auth.password_reset.requested", t)).toBe(
      "Recuperação de senha pedida",
    );
  });

  it("test_audit_action_label_falls_back_to_raw_code", () => {
    expect(auditActionLabel("connector.synced", t)).toBe("connector.synced");
    expect(auditActionLabel("toString", t)).toBe("toString");
  });

  it("test_audit_action_label_covers_every_contract_action", () => {
    for (const action of AUDIT_ACTIONS) {
      expect(auditActionLabel(action, t)).not.toBe(action);
    }
  });
});
