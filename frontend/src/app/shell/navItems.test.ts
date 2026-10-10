import { describe, expect, it } from "vitest";

import { WORKSPACE_ID } from "@/test/factories";

import { adminNavItems, areaMinRole, workspaceNavItems, type WorkspaceArea } from "./navItems";

function keysFor(role: "owner" | "admin" | "editor" | "viewer") {
  return workspaceNavItems(WORKSPACE_ID, role).map(({ key }) => key);
}

describe("workspaceNavItems", () => {
  it("test_workspace_nav_items_for_viewer_hide_management_areas", () => {
    expect(keysFor("viewer")).toEqual([
      "home",
      "chat",
      "sources",
      "pipelines",
      "collections",
      "channels",
    ]);
  });

  it("test_workspace_nav_items_for_editor_add_assistants_and_providers", () => {
    expect(keysFor("editor")).toEqual([
      "home",
      "chat",
      "assistants",
      "providers",
      "sources",
      "pipelines",
      "collections",
      "channels",
    ]);
  });

  it("test_workspace_nav_items_for_admin_and_owner_show_everything", () => {
    const all = [
      "home",
      "chat",
      "conversations",
      "assistants",
      "providers",
      "sources",
      "pipelines",
      "collections",
      "channels",
      "members",
      "settings",
      "audit",
    ];
    expect(keysFor("admin")).toEqual(all);
    expect(keysFor("owner")).toEqual(all);
  });

  it("test_workspace_nav_items_build_urls_under_workspace", () => {
    const [home, chat] = workspaceNavItems(WORKSPACE_ID, "viewer");

    expect(home).toMatchObject({ to: `/w/${WORKSPACE_ID}`, end: true });
    expect(chat).toMatchObject({ to: `/w/${WORKSPACE_ID}/chat`, end: false });
  });
});

describe("adminNavItems", () => {
  it("test_admin_nav_items_point_to_admin_pages", () => {
    expect(adminNavItems().map(({ to }) => to)).toEqual([
      "/admin/workspaces",
      "/admin/users",
      "/admin/audit",
    ]);
  });
});

describe("areaMinRole", () => {
  it("test_area_min_role_reads_the_menu_table", () => {
    expect(areaMinRole("members")).toBe("admin");
    expect(areaMinRole("assistants")).toBe("editor");
    expect(areaMinRole("sources")).toBe("viewer");
  });

  it("test_area_min_role_rejects_unknown_area", () => {
    expect(() => areaMinRole("unknown" as WorkspaceArea)).toThrow("Unknown workspace area");
  });
});
