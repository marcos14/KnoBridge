import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeMe } from "@/test/factories";
import { setupAlreadyCompleted, setupStatusNeeded } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { meQueryKey, setupStatusQueryKey } from "./auth";
import { useRunSetup, useSetupStatus } from "./setup";

describe("useSetupStatus", () => {
  it("test_use_setup_status_reports_done_instance", async () => {
    const { result } = renderQueryHook(() => useSetupStatus());

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual({ needs_setup: false });
  });

  it("test_use_setup_status_reports_fresh_instance", async () => {
    server.use(setupStatusNeeded);
    const { result } = renderQueryHook(() => useSetupStatus());

    await waitFor(() => {
      expect(result.current.data).toEqual({ needs_setup: true });
    });
  });
});

describe("useRunSetup", () => {
  const input = {
    name: "Ana Teste",
    email: "ana@example.test",
    password: "a-long-passphrase",
    workspace_name: "Acme Suporte",
  };

  it("test_use_run_setup_fills_me_and_marks_setup_done", async () => {
    const { result, queryClient } = renderQueryHook(() => useRunSetup());
    queryClient.setQueryData(setupStatusQueryKey, { needs_setup: true });

    await act(() => result.current.mutateAsync(input));

    expect(queryClient.getQueryData(setupStatusQueryKey)).toEqual({ needs_setup: false });
    expect(queryClient.getQueryData(meQueryKey)).toEqual(
      makeMe({ is_superadmin: true, workspaces: [] }),
    );
  });

  it("test_use_run_setup_fails_when_already_completed", async () => {
    server.use(setupAlreadyCompleted);
    const { result } = renderQueryHook(() => useRunSetup());

    act(() => {
      result.current.mutate(input);
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ status: 409, code: "setup_already_completed" });
  });
});
