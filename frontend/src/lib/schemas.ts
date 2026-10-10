import type { TFunction } from "i18next";
import { z } from "zod";

/** Password policy of the backend (`security/passwords.py`): length only, no composition rules. */
export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 1024;
/** Limits of the contract (`docs/specs/openapi.json`). */
export const NAME_MAX_LENGTH = 200;
export const EMAIL_MAX_LENGTH = 320;

/** Display name of a new account. */
export function nameField(t: TFunction) {
  return z
    .string()
    .trim()
    .min(1, { error: t("auth.validation.nameRequired") })
    .max(NAME_MAX_LENGTH, { error: t("auth.validation.tooLong", { max: NAME_MAX_LENGTH }) });
}

/** Address typed by the user, checked for an e-mail shape. */
export function emailField(t: TFunction) {
  return z
    .string()
    .trim()
    .min(1, { error: t("auth.validation.emailRequired") })
    .max(EMAIL_MAX_LENGTH, { error: t("auth.validation.tooLong", { max: EMAIL_MAX_LENGTH }) })
    .pipe(z.email({ error: t("auth.validation.emailInvalid") }));
}

/** Fields of a new password and its confirmation; pair them with `withMatchingPasswords`. */
export function newPasswordFields(t: TFunction) {
  return {
    password: z
      .string()
      .min(PASSWORD_MIN_LENGTH, {
        error: t("auth.validation.passwordTooShort", { min: PASSWORD_MIN_LENGTH }),
      })
      .max(PASSWORD_MAX_LENGTH, {
        error: t("auth.validation.tooLong", { max: PASSWORD_MAX_LENGTH }),
      }),
    confirmPassword: z.string(),
  };
}

export interface NewPasswordValues {
  password: string;
  confirmPassword: string;
}

/** Rejects a confirmation that differs from the password, reporting it on `confirmPassword`. */
export function withMatchingPasswords<Schema extends z.ZodType<NewPasswordValues>>(
  schema: Schema,
  t: TFunction,
): Schema {
  return schema.refine((values) => values.password === values.confirmPassword, {
    path: ["confirmPassword"],
    error: t("auth.validation.passwordMismatch"),
  });
}
