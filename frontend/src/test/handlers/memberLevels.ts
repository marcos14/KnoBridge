import { http, HttpResponse } from "msw";

import type { MemberLevels, ProductRef } from "@/lib/api/memberLevels";
import type { components } from "@/lib/api/schema.gen";
import { defaultMaxLevel } from "@/lib/responseLevels";

import { makeMemberLevels, makeProductRefs } from "../levelFactories";
import { apiErrorResponse } from "./errors";

type MemberLevelsPage = components["schemas"]["MemberLevelsPage"];
type ProductLevelsUpdate = components["schemas"]["ProductLevelsUpdate"];

const MEMBER_LEVELS = "*/v1/workspaces/:workspaceId/member-levels";
const PRODUCT_LEVELS = "*/v1/workspaces/:workspaceId/members/:userId/product-levels";

/** One page of the table, filtered by `query` (name or e-mail) and `role` like the API. */
function levelsPage(request: Request, products: ProductRef[], members: readonly MemberLevels[]) {
  const search = new URL(request.url).searchParams;
  const role = search.get("role");
  const query = search.get("query")?.toLowerCase() ?? "";
  const rows = members.filter(
    (item) =>
      `${item.name} ${item.email}`.toLowerCase().includes(query) &&
      (role === null || item.role === role),
  );
  const limit = Number(search.get("limit") ?? "50");
  const offset = Number(search.get("offset") ?? "0");
  return HttpResponse.json<MemberLevelsPage>({
    products,
    items: rows.slice(offset, offset + limit),
    total: rows.length,
    limit,
    offset,
  });
}

/** `member` with each change of `body` applied (`null` back to the default of the role). */
function applyLevels(member: MemberLevels, body: ProductLevelsUpdate): MemberLevels {
  return {
    ...member,
    levels: member.levels.map((level) => {
      const change = body.levels.find((item) => item.product_id === level.product_id);
      if (change === undefined) {
        return level;
      }
      return change.max_level === null
        ? { ...level, max_level: defaultMaxLevel(member.role), explicit: false }
        : { ...level, max_level: change.max_level, explicit: true };
    }),
  };
}

/** GET .../member-levels answering `members` (default `makeMemberLevels()`) and `products`. */
export function memberLevelsAs(
  members: MemberLevels[] = makeMemberLevels(),
  products: ProductRef[] = makeProductRefs(),
) {
  return http.get(MEMBER_LEVELS, ({ request }) => levelsPage(request, products, members));
}

interface MemberLevelStoreOptions {
  products?: ProductRef[];
  members?: MemberLevels[];
}

/**
 * The member × product table that really changes: the `GET` pages `members` (default
 * `makeMemberLevels()` over `makeProductRefs()`) and records each query string in `queries`; the
 * `PUT .../members/{id}/product-levels` applies each `{product_id, max_level}` (`null` back to the
 * role's default), 404 `not_found` for someone else and 422 `member_level_product_invalid` for an
 * unknown product, and records the bodies in `changes`.
 */
export function memberLevelStore(options: MemberLevelStoreOptions = {}) {
  const products = options.products ?? makeProductRefs();
  let members = options.members ?? makeMemberLevels(products);
  const queries: URLSearchParams[] = [];
  const changes: { userId: string; body: ProductLevelsUpdate }[] = [];
  const handlers = [
    http.get(MEMBER_LEVELS, ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return levelsPage(request, products, members);
    }),
    http.put(PRODUCT_LEVELS, async ({ params, request }) => {
      const userId = String(params.userId);
      const body = (await request.json()) as ProductLevelsUpdate;
      const member = members.find((item) => item.user_id === userId);
      if (member === undefined) {
        return apiErrorResponse(404, "not_found");
      }
      const unknown = body.levels.filter(
        (level) => !products.some((product) => product.id === level.product_id),
      );
      if (unknown.length > 0) {
        return apiErrorResponse(422, "member_level_product_invalid", {
          product_ids: unknown.map((level) => level.product_id),
        });
      }
      const updated = applyLevels(member, body);
      members = members.map((item) => (item.user_id === userId ? updated : item));
      changes.push({ userId, body });
      return HttpResponse.json<MemberLevels>(updated);
    }),
  ];
  return { handlers, queries, changes };
}

/** GET .../member-levels failing on the server (500). */
export const memberLevelsServerError = http.get(MEMBER_LEVELS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** PUT .../members/{user_id}/product-levels refused with `status` and `code`. */
export function setMemberLevelFails(status: number, code: string) {
  return http.put(PRODUCT_LEVELS, () => apiErrorResponse(status, code));
}

/** Stateless defaults: the default table and a `PUT` answering the default row changed. */
export const memberLevelsHandlers = [
  memberLevelsAs(),
  http.put(PRODUCT_LEVELS, async ({ params, request }) => {
    const body = (await request.json()) as ProductLevelsUpdate;
    const member = makeMemberLevels().find((item) => item.user_id === String(params.userId));
    return member === undefined
      ? apiErrorResponse(404, "not_found")
      : HttpResponse.json<MemberLevels>(applyLevels(member, body));
  }),
];
