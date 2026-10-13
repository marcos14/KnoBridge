import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { type Me, meQueryKey } from "./auth";
import { apiClient, unwrap } from "./client";
import type { ResponseLevel } from "./levels";
import { membersQueryKey } from "./members";
import { productsQueryKey } from "./products";
import type { components, operations } from "./schema.gen";

export type MemberLevels = components["schemas"]["MemberLevelsOut"];
export type MemberProductLevel = components["schemas"]["MemberProductLevelOut"];
export type ProductRef = components["schemas"]["ProductRefOut"];

/** Search, role filter, sort and page of `GET .../member-levels` (the same as the member list). */
export type MemberLevelsQuery = NonNullable<
  operations["list_member_levels_v1_workspaces__workspace_id__member_levels_get"]["parameters"]["query"]
>;

/** Under the members' key, so a role change or a removal reloads the levels too. */
export function memberLevelsQueryKey(workspaceId: string) {
  return [...membersQueryKey(workspaceId), "levels"] as const;
}

/**
 * `GET .../member-levels` (owner or admin): one page of the member × product table, with every
 * product (active and inactive, by name) and, per member, one level per product in that order.
 * The previous page stays on screen while the next one loads.
 */
export function useMemberLevelsPage(workspaceId: string, query: MemberLevelsQuery) {
  return useQuery({
    queryKey: [...memberLevelsQueryKey(workspaceId), query],
    queryFn: async ({ signal }) =>
      unwrap(
        await apiClient.GET("/v1/workspaces/{workspace_id}/member-levels", {
          params: { path: { workspace_id: workspaceId }, query },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export interface MemberLevelChange {
  userId: string;
  productId: string;
  /** `null` drops the stored value: the member goes back to the default of their role. */
  maxLevel: ResponseLevel | null;
}

/**
 * `PUT .../members/{user_id}/product-levels` (owner or admin) for one product; the other products
 * stay as they are. 403 `role_not_allowed` (member above the editor's role), 404 `not_found`, 422
 * `member_level_product_invalid`. Reloads the table and, when the member is the logged-in user,
 * `me` and the products, which carry their own level.
 */
export function useSetMemberLevel(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, productId, maxLevel }: MemberLevelChange) =>
      unwrap(
        await apiClient.PUT("/v1/workspaces/{workspace_id}/members/{user_id}/product-levels", {
          params: { path: { workspace_id: workspaceId, user_id: userId } },
          body: { levels: [{ product_id: productId, max_level: maxLevel }] },
        }),
      ),
    onSuccess: async (_levels, { userId }) => {
      const self = queryClient.getQueryData<Me | null>(meQueryKey)?.user.id === userId;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: memberLevelsQueryKey(workspaceId) }),
        ...(self
          ? [
              queryClient.invalidateQueries({ queryKey: meQueryKey }),
              queryClient.invalidateQueries({ queryKey: productsQueryKey(workspaceId) }),
            ]
          : []),
      ]);
    },
  });
}
