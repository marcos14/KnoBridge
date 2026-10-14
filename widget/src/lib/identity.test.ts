import { describe, expect, it } from "vitest";

import { IDENTITY, identityOf } from "../test/fake-api.ts";
import { identitySub, UNREADABLE_SUB } from "./identity.ts";

describe("identitySub", () => {
  it("test_identity_sub_reads_the_spec_example", () => {
    expect(identitySub(IDENTITY)).toBe("cliente-42");
  });

  it("test_identity_sub_is_null_without_identity", () => {
    expect(identitySub(null)).toBeNull();
    expect(identitySub(undefined)).toBeNull();
    expect(identitySub("")).toBeNull();
  });

  it("test_identity_sub_decodes_utf8_and_url_safe_characters", () => {
    const sub = "joão~~~???>>>";
    const identity = identityOf({ sub });

    expect(identity.split(".")[1]).toMatch(/[-_]/);
    expect(identitySub(identity)).toBe(sub);
  });

  it.each([
    ["two parts", "v1.abc"],
    ["another version", IDENTITY.replace(/^v1/, "v2")],
    ["empty payload", "v1..sig"],
    ["not base64", "v1.@@@.sig"],
    ["not json", `v1.${btoa("nope")}.sig`],
    ["json null", identityOf({}).replace(/^v1\.[^.]+/, `v1.${btoa("null")}`)],
    ["no sub", identityOf({ name: "Ana" })],
    ["sub not text", identityOf({ sub: 42 })],
    ["empty sub", identityOf({ sub: "" })],
    ["sub too long", identityOf({ sub: "x".repeat(201) })],
  ])("test_identity_sub_is_unreadable_with_%s", (_case, identity) => {
    expect(identitySub(identity)).toBe(UNREADABLE_SUB);
  });
});
