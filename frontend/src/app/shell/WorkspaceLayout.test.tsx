import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";
import { readLastWorkspaceId } from "@/lib/lastWorkspace";
import { makeMe, makeWorkspace, OTHER_WORKSPACE_ID, WORKSPACE_ID } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { isWorkspaceSuspendedError } from "./useWorkspaceSuspended";

const suspendedError = new ApiError(403, "workspace_suspended");

describe("WorkspaceLayout", () => {
  it("test_workspace_layout_remembers_last_used_workspace", async () => {
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources` });

    await screen.findByRole("heading", { level: 1, name: "Fontes" });

    expect(readLastWorkspaceId()).toBe(WORKSPACE_ID);
  });

  it("test_workspace_layout_shows_suspended_state_from_membership", async () => {
    server.use(meAs(makeMe({ workspaces: [makeWorkspace({ status: "suspended" })] })));
    renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources` });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Workspace suspenso" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Fontes" })).not.toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
  });

  it("test_workspace_layout_shows_suspended_state_when_a_query_gets_workspace_suspended", async () => {
    const { queryClient } = renderWithProviders({ path: `/w/${WORKSPACE_ID}/sources` });
    await screen.findByRole("heading", { level: 1, name: "Fontes" });

    await act(async () => {
      await queryClient
        .query({
          queryKey: ["api", "workspaces", WORKSPACE_ID, "sources"],
          queryFn: () => Promise.reject(suspendedError),
        })
        .catch(() => undefined);
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Workspace suspenso" }),
    ).toBeInTheDocument();
  });

  it("test_workspace_layout_shows_suspended_state_when_a_mutation_gets_workspace_suspended", async () => {
    const { queryClient } = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });
    await screen.findByRole("heading", { level: 1, name: "Início" });

    await act(async () => {
      await queryClient
        .getMutationCache()
        .build(queryClient, { mutationFn: () => Promise.reject(suspendedError) })
        .execute(undefined)
        .catch(() => undefined);
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Workspace suspenso" }),
    ).toBeInTheDocument();
  });

  it("test_workspace_layout_ignores_other_errors", async () => {
    const { queryClient } = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });
    await screen.findByRole("heading", { level: 1, name: "Início" });

    await act(async () => {
      await queryClient
        .query({
          queryKey: ["api", "other"],
          queryFn: () => Promise.reject(new ApiError(403, "forbidden")),
        })
        .catch(() => undefined);
    });

    expect(screen.getByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
  });

  it("test_workspace_layout_suspension_does_not_leak_to_next_workspace", async () => {
    const user = userEvent.setup();
    server.use(
      meAs(
        makeMe({
          workspaces: [makeWorkspace(), makeWorkspace({ id: OTHER_WORKSPACE_ID, name: "Beta" })],
        }),
      ),
    );
    const { queryClient } = renderWithProviders({ path: `/w/${WORKSPACE_ID}` });
    await screen.findByRole("heading", { level: 1, name: "Início" });
    await act(async () => {
      await queryClient
        .query({ queryKey: ["api", "x"], queryFn: () => Promise.reject(suspendedError) })
        .catch(() => undefined);
    });
    await screen.findByRole("heading", { level: 1, name: "Workspace suspenso" });

    await user.click(screen.getByRole("button", { name: "Trocar de workspace" }));
    await user.click(screen.getByRole("menuitemradio", { name: "Beta" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
    });
  });
});

describe("isWorkspaceSuspendedError", () => {
  it("test_is_workspace_suspended_error_matches_only_the_403_code", () => {
    expect(isWorkspaceSuspendedError(suspendedError)).toBe(true);
    expect(isWorkspaceSuspendedError(new ApiError(403, "forbidden"))).toBe(false);
    expect(isWorkspaceSuspendedError(new ApiError(409, "workspace_suspended"))).toBe(false);
    expect(isWorkspaceSuspendedError(new Error("workspace_suspended"))).toBe(false);
  });
});
