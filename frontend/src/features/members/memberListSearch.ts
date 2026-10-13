import { type ListSearchSpec, oneOf } from "@/lib/listSearch";
import { ROLES } from "@/lib/roles";

/** Sorts of the member list and of the levels table (the first is the default). */
export const MEMBER_SORTS = ["name", "-name", "email", "role", "-joined_at", "joined_at"] as const;

/** Search, role filter and sort of the member list and the levels table, in the URL. */
export const MEMBER_LIST: ListSearchSpec<"role", (typeof MEMBER_SORTS)[number]> = {
  filters: { role: oneOf(ROLES) },
  sorts: MEMBER_SORTS,
};
