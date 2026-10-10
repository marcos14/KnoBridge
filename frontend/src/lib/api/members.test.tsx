import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMember, memberId, USER_ID, WORKSPACE_ID } from "@/test/factories";
import { membersAs, memberStore } from "@/test/handlers";
import { renderQueryHook } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { useMe } from "./auth";
import { useChangeMemberRole, useMembers, useRemoveMember } from "./members";

const MEMBERS_PATH = "*/v1/workspaces/:workspaceId/members";

function countMeRequests() {
  const calls: string[] = [];
  server.use(
    http.get("*/v1/me", ({ request }) => {
      calls.push(request.url);
      return undefined;
    }),
  );
  return calls;
}

describe("useMembers", () => {
  it("test_use_members_reads_every_page", async () => {
    const offsets: string[] = [];
    const many = Array.from({ length: 250 }, (_, index) =>
      makeMember({ user_id: memberId(index) }),
    );
    server.use(
      http.get(MEMBERS_PATH, ({ request }) => {
        offsets.push(new URL(request.url).searchParams.get("offset") ?? "");
        return undefined;
      }),
      membersAs(many),
    );
    const { result } = renderQueryHook(() => useMembers(WORKSPACE_ID));

    await waitFor(() => {
      expect(result.current.data).toHaveLength(250);
    });
    expect(offsets).toEqual(["0", "200"]);
  });

  it("test_use_members_stops_on_empty_page", async () => {
    server.use(
      http.get(MEMBERS_PATH, () =>
        HttpResponse.json({ items: [], total: 3, limit: 200, offset: 0 }),
      ),
    );
    const { result } = renderQueryHook(() => useMembers(WORKSPACE_ID));

    await waitFor(() => {
      expect(result.current.data).toEqual([]);
    });
  });
});

describe("member changes", () => {
  it("test_change_member_role_of_self_refreshes_me", async () => {
    const store = memberStore();
    server.use(...store.handlers);
    const calls = countMeRequests();
    const { result } = renderQueryHook(() => ({
      me: useMe(),
      change: useChangeMemberRole(WORKSPACE_ID),
    }));
    await waitFor(() => {
      expect(result.current.me.isSuccess).toBe(true);
    });

    await act(() => result.current.change.mutateAsync({ userId: USER_ID, role: "admin" }));

    expect(calls).toHaveLength(2);
  });

  it("test_remove_other_member_keeps_me", async () => {
    const store = memberStore();
    server.use(...store.handlers);
    const calls = countMeRequests();
    const { result } = renderQueryHook(() => ({
      me: useMe(),
      remove: useRemoveMember(WORKSPACE_ID),
    }));
    await waitFor(() => {
      expect(result.current.me.isSuccess).toBe(true);
    });

    await act(() => result.current.remove.mutateAsync(memberId(2)));

    expect(calls).toHaveLength(1);
    expect(store.removed).toEqual([memberId(2)]);
  });
});
