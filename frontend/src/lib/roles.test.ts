import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";

import { canHandleRole, canManageWorkspace, findWorkspace, hasRole, ROLES } from "./roles";

describe("ROLES", () => {
  it("test_roles_go_from_most_to_least_privileged", () => {
    expect(ROLES).toEqual(["owner", "admin", "editor", "viewer"]);
  });
});

describe("canManageWorkspace", () => {
  it.each([
    ["owner", true],
    ["admin", true],
    ["editor", false],
    ["viewer", false],
  ] as const)("test_can_manage_workspace_%s_is_%s", (role, expected) => {
    expect(canManageWorkspace(role)).toBe(expected);
  });
});

describe("canHandleRole", () => {
  it.each([
    ["owner", "owner", true],
    ["owner", "viewer", true],
    ["admin", "owner", false],
    ["admin", "admin", true],
    ["admin", "editor", true],
    ["editor", "viewer", false],
    ["viewer", "viewer", false],
  ] as const)("test_can_handle_role_%s_handles_%s_is_%s", (actor, role, expected) => {
    expect(canHandleRole(actor, role)).toBe(expected);
  });
});

describe("hasRole", () => {
  it.each([
    ["owner", "admin", true],
    ["admin", "admin", true],
    ["editor", "admin", false],
    ["viewer", "editor", false],
    ["viewer", "viewer", true],
    ["admin", "owner", false],
  ] as const)("test_has_role_%s_meets_%s_is_%s", (role, minRole, expected) => {
    expect(hasRole(role, minRole)).toBe(expected);
  });
});

describe("findWorkspace", () => {
  it("test_find_workspace_returns_membership_by_id", () => {
    const other = makeWorkspace({ id: OTHER_WORKSPACE_ID, role: "viewer" });
    const me = makeMe({ workspaces: [makeWorkspace(), other] });

    expect(findWorkspace(me, OTHER_WORKSPACE_ID)).toBe(other);
  });

  it("test_find_workspace_returns_undefined_for_non_member", () => {
    expect(findWorkspace(makeMe(), OTHER_WORKSPACE_ID)).toBeUndefined();
  });

  it("test_find_workspace_returns_undefined_without_session_or_id", () => {
    expect(findWorkspace(null, WORKSPACE_ID)).toBeUndefined();
    expect(findWorkspace(undefined, WORKSPACE_ID)).toBeUndefined();
    expect(findWorkspace(makeMe(), undefined)).toBeUndefined();
  });
});
