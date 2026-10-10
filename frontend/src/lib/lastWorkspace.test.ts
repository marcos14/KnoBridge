import { describe, expect, it } from "vitest";

import { makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";

import { pickWorkspace, readLastWorkspaceId, storeLastWorkspaceId } from "./lastWorkspace";

const first = makeWorkspace();
const second = makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Beta" });

describe("lastWorkspace", () => {
  it("test_last_workspace_round_trips_through_storage", () => {
    expect(readLastWorkspaceId()).toBeUndefined();

    storeLastWorkspaceId(OTHER_WORKSPACE_ID);

    expect(readLastWorkspaceId()).toBe(OTHER_WORKSPACE_ID);
  });
});

describe("pickWorkspace", () => {
  it("test_pick_workspace_prefers_last_used", () => {
    expect(pickWorkspace([first, second], OTHER_WORKSPACE_ID)).toBe(second);
  });

  it("test_pick_workspace_falls_back_to_first_when_no_longer_member", () => {
    expect(pickWorkspace([first, second], "gone")).toBe(first);
    expect(pickWorkspace([first, second], undefined)).toBe(first);
  });

  it("test_pick_workspace_skips_suspended_workspaces", () => {
    const suspended = makeWorkspace({ status: "suspended" });

    expect(pickWorkspace([suspended, second], WORKSPACE_ID)).toBe(second);
  });

  it("test_pick_workspace_returns_suspended_when_nothing_else", () => {
    const suspended = makeWorkspace({ status: "suspended" });

    expect(pickWorkspace([suspended], undefined)).toBe(suspended);
  });

  it("test_pick_workspace_returns_undefined_without_workspaces", () => {
    expect(pickWorkspace([], WORKSPACE_ID)).toBeUndefined();
  });
});
