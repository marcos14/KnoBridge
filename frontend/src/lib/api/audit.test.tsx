import { waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WORKSPACE_ID } from "@/test/factories";
import { auditRecorder } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { useInstanceAudit, useWorkspaceAudit } from "./audit";

describe("useWorkspaceAudit", () => {
  it("test_use_workspace_audit_sends_filters_with_api_names", async () => {
    const recorder = auditRecorder("workspace");
    server.use(recorder.handler);
    const { result } = renderQueryHook(() =>
      useWorkspaceAudit(WORKSPACE_ID, {
        action: "membership.removed",
        actorUserId: "00000000-0000-4000-8000-000000000101",
        occurredFrom: "2026-10-01T03:00:00.000Z",
        occurredTo: "2026-10-02T03:00:00.000Z",
        limit: 20,
        offset: 40,
      }),
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(Object.fromEntries(recorder.queries[0] ?? [])).toEqual({
      action: "membership.removed",
      actor_user_id: "00000000-0000-4000-8000-000000000101",
      occurred_from: "2026-10-01T03:00:00.000Z",
      occurred_to: "2026-10-02T03:00:00.000Z",
      limit: "20",
      offset: "40",
    });
  });
});

describe("useInstanceAudit", () => {
  it("test_use_instance_audit_omits_unset_filters", async () => {
    const recorder = auditRecorder("instance");
    server.use(recorder.handler);
    const { result } = renderQueryHook(() => useInstanceAudit({ limit: 20, offset: 0 }));

    await waitFor(() => {
      expect(result.current.data?.total).toBe(4);
    });
    expect(recorder.queries[0]?.toString()).toBe("limit=20&offset=0");
  });
});
