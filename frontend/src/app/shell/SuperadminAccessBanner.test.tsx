import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { leaveWorkspaceAccessFails, workspaceAccessStore } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const BANNER = "Acesso de superadmin";
const NAMES = { [OTHER_WORKSPACE_ID]: "Beta Help", [WORKSPACE_ID]: "Acme Suporte" };

/** Superadmin member of Acme only, entered in Beta Help (or in `startIn`). */
function withAccess(startIn = OTHER_WORKSPACE_ID, base = makeMe({ is_superadmin: true })) {
  const store = workspaceAccessStore(base, NAMES, startIn);
  server.use(...store.handlers);
  return store;
}

async function renderAt(path: string) {
  const result = renderWithProviders({ path });
  await screen.findByRole("heading", { level: 1 });
  return result;
}

describe("SuperadminAccessBanner", () => {
  it("test_superadmin_access_banner_is_hidden_without_access", async () => {
    server.use(...workspaceAccessStore().handlers);
    await renderAt(`/w/${WORKSPACE_ID}`);

    expect(screen.queryByRole("region", { name: BANNER })).not.toBeInTheDocument();
  });

  it("test_superadmin_access_banner_inside_workspace_marks_switcher", async () => {
    const user = userEvent.setup();
    withAccess();
    await renderAt(`/w/${OTHER_WORKSPACE_ID}`);

    const banner = await screen.findByRole("region", { name: BANNER });
    expect(banner).toHaveTextContent("Acesso de superadmin a Beta Help");
    expect(within(banner).queryByRole("link")).not.toBeInTheDocument();
    const switcher = screen.getByRole("button", { name: "Trocar de workspace" });
    expect(switcher).toHaveTextContent("Beta Help");
    await user.click(switcher);
    const item = screen.getByRole("menuitemradio", { name: /^Beta Help/ });
    expect(item).toHaveAttribute("aria-checked", "true");
    expect(item).toHaveTextContent("superadmin");
  });

  it("test_superadmin_access_banner_outside_workspace_links_to_it", async () => {
    const user = userEvent.setup();
    withAccess();
    const { router } = await renderAt("/admin/workspaces");

    const banner = await screen.findByRole("region", { name: BANNER });
    await user.click(within(banner).getByRole("link", { name: "Abrir Beta Help" }));

    expect(router.state.location.pathname).toBe(`/w/${OTHER_WORKSPACE_ID}`);
  });

  it("test_superadmin_access_leave_inside_goes_back_to_admin_workspaces", async () => {
    const user = userEvent.setup();
    const store = withAccess();
    const { router } = await renderAt(`/w/${OTHER_WORKSPACE_ID}`);

    const banner = await screen.findByRole("region", { name: BANNER });
    await user.click(
      within(banner).getByRole("button", { name: "Sair do acesso de superadmin a Beta Help" }),
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "Workspaces da instância" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/admin/workspaces");
    expect(store.left).toBe(1);
    expect(screen.queryByRole("region", { name: BANNER })).not.toBeInTheDocument();
  });

  it("test_superadmin_access_leave_as_member_stays_in_workspace", async () => {
    const user = userEvent.setup();
    withAccess(
      WORKSPACE_ID,
      makeMe({ is_superadmin: true, workspaces: [makeWorkspace({ role: "viewer" })] }),
    );
    const { router } = await renderAt(`/w/${WORKSPACE_ID}`);

    const banner = await screen.findByRole("region", { name: BANNER });
    await user.click(within(banner).getByRole("button", { name: /^Sair do acesso/ }));

    expect(await screen.findByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: BANNER })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
  });

  it("test_superadmin_access_leave_outside_stays_on_page", async () => {
    const user = userEvent.setup();
    withAccess();
    const { router } = await renderAt(`/w/${WORKSPACE_ID}`);

    const banner = await screen.findByRole("region", { name: BANNER });
    await user.click(within(banner).getByRole("button", { name: /^Sair do acesso/ }));

    await screen.findByRole("heading", { level: 1, name: "Início" });
    expect(screen.queryByRole("region", { name: BANNER })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/w/${WORKSPACE_ID}`);
  });

  it("test_superadmin_access_leave_disables_button_while_sending", async () => {
    const user = userEvent.setup();
    withAccess();
    server.use(
      http.delete("*/v1/admin/workspace-access", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    await renderAt("/admin/workspaces");

    const banner = await screen.findByRole("region", { name: BANNER });
    await user.click(within(banner).getByRole("button", { name: /^Sair do acesso/ }));

    expect(within(banner).getByRole("button", { name: /^Sair do acesso/ })).toBeDisabled();
    expect(within(banner).getByText("Saindo…")).toBeInTheDocument();
  });

  it("test_superadmin_access_leave_error_is_shown", async () => {
    const user = userEvent.setup();
    withAccess();
    server.use(leaveWorkspaceAccessFails(403, "csrf_failed"));
    await renderAt("/admin/workspaces");

    const banner = await screen.findByRole("region", { name: BANNER });
    await user.click(within(banner).getByRole("button", { name: /^Sair do acesso/ }));

    expect(await within(banner).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: BANNER })).toBeInTheDocument();
  });
});
