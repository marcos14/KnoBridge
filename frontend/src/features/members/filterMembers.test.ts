import { describe, expect, it } from "vitest";

import { makeMember, makeMembers } from "@/test/factories";

import { filterMembers } from "./filterMembers";

function names(query: string, members = makeMembers()) {
  return filterMembers(members, query).map((member) => member.name);
}

describe("filterMembers", () => {
  it("test_filter_members_blank_query_keeps_everyone", () => {
    const members = makeMembers();

    expect(filterMembers(members, "   ")).toBe(members);
  });

  it("test_filter_members_matches_name_ignoring_case", () => {
    expect(names("CARLA")).toEqual(["Carla Souza"]);
  });

  it("test_filter_members_matches_email", () => {
    expect(names("davi@")).toEqual(["Davi Rocha"]);
  });

  it("test_filter_members_ignores_accents", () => {
    const members = [makeMember({ name: "João Antônio" }), makeMember({ name: "Maria" })];

    expect(names("joao anto", members)).toEqual(["João Antônio"]);
  });

  it("test_filter_members_no_match_is_empty", () => {
    expect(names("zz")).toEqual([]);
  });
});
