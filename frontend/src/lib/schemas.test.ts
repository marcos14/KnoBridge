import { describe, expect, it } from "vitest";
import { z } from "zod";

import { i18n } from "@/i18n";

import {
  emailField,
  nameField,
  newPasswordFields,
  optionalSlugField,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  SLUG_MAX_LENGTH,
  withMatchingPasswords,
  workspaceNameField,
} from "./schemas";

const t = i18n.t;

function firstMessage(result: { success: boolean; error?: z.ZodError }) {
  return result.error?.issues[0]?.message;
}

describe("auth schemas", () => {
  it("test_name_field_trims_and_requires_value", () => {
    expect(nameField(t).parse("  Ana  ")).toBe("Ana");
    expect(firstMessage(nameField(t).safeParse("   "))).toBe("Informe seu nome.");
  });

  it("test_name_field_limits_length", () => {
    expect(firstMessage(nameField(t).safeParse("a".repeat(201)))).toBe(
      "Use no máximo 200 caracteres.",
    );
  });

  it("test_email_field_trims_and_checks_shape", () => {
    expect(emailField(t).parse(" ana@example.test ")).toBe("ana@example.test");
    expect(firstMessage(emailField(t).safeParse(""))).toBe("Informe seu e-mail.");
    expect(firstMessage(emailField(t).safeParse("ana@"))).toBe("Informe um e-mail válido.");
  });

  it("test_new_password_respects_backend_length_policy", () => {
    const schema = withMatchingPasswords(z.object(newPasswordFields(t)), t);
    const exact = "a".repeat(PASSWORD_MIN_LENGTH);
    const tooLong = "a".repeat(PASSWORD_MAX_LENGTH + 1);

    expect(schema.safeParse({ password: exact, confirmPassword: exact }).success).toBe(true);
    expect(firstMessage(schema.safeParse({ password: "a".repeat(11), confirmPassword: "" }))).toBe(
      "A senha precisa ter ao menos 12 caracteres.",
    );
    expect(firstMessage(schema.safeParse({ password: tooLong, confirmPassword: tooLong }))).toBe(
      "Use no máximo 1024 caracteres.",
    );
  });

  it("test_new_password_reports_mismatch_on_confirmation", () => {
    const schema = withMatchingPasswords(z.object(newPasswordFields(t)), t);

    const result = schema.safeParse({
      password: "uma-frase-longa-e-segura",
      confirmPassword: "outra-frase-longa",
    });

    expect(result.error?.issues).toEqual([
      expect.objectContaining({ path: ["confirmPassword"], message: "As senhas não conferem." }),
    ]);
  });
});

describe("workspace schemas", () => {
  it("test_workspace_name_field_trims_requires_and_limits", () => {
    expect(workspaceNameField(t).parse("  Acme  ")).toBe("Acme");
    expect(firstMessage(workspaceNameField(t).safeParse(" "))).toBe("Informe o nome do workspace.");
    expect(firstMessage(workspaceNameField(t).safeParse("a".repeat(201)))).toBe(
      "Use no máximo 200 caracteres.",
    );
  });
});

describe("optionalSlugField", () => {
  it("test_optional_slug_field_accepts_blank_and_valid_slugs", () => {
    expect(optionalSlugField(t).parse("  ")).toBe("");
    expect(optionalSlugField(t).parse(" acme-suporte-2 ")).toBe("acme-suporte-2");
  });

  it("test_optional_slug_field_rejects_invalid_shapes", () => {
    for (const slug of ["Acme", "-acme", "acme-", "acme--x", "acme x"]) {
      expect(firstMessage(optionalSlugField(t).safeParse(slug))).toBe(
        "Use só letras minúsculas, números e hífens, sem hífen no início nem no fim.",
      );
    }
  });

  it("test_optional_slug_field_limits_length", () => {
    expect(firstMessage(optionalSlugField(t).safeParse("a".repeat(SLUG_MAX_LENGTH + 1)))).toBe(
      "Use no máximo 64 caracteres.",
    );
  });
});
