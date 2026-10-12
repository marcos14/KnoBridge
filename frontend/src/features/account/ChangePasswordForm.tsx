import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { useChangePassword } from "@/lib/api/account";
import { isApiErrorCode } from "@/lib/api/client";
import {
  newPasswordFields,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  withMatchingPasswords,
} from "@/lib/schemas";

import { AccountSection } from "./AccountSection";

const EMPTY = { currentPassword: "", password: "", confirmPassword: "" };

/** Replaces the password (`POST /v1/me/password`); the other sessions end, this one stays. */
export function ChangePasswordForm() {
  const { t } = useTranslation();
  const change = useChangePassword();
  const schema = useMemo(
    () =>
      withMatchingPasswords(
        z.object({
          currentPassword: z
            .string()
            .min(1, { error: t("auth.validation.passwordRequired") })
            .max(PASSWORD_MAX_LENGTH, {
              error: t("auth.validation.tooLong", { max: PASSWORD_MAX_LENGTH }),
            }),
          ...newPasswordFields(t),
        }),
        t,
      ),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY,
  });
  // A wrong current password is shown on its field; other refusals above the form.
  const wrongCurrent = isApiErrorCode(change.error, "invalid_current_password");

  return (
    <AccountSection
      title={t("account.security.password.title")}
      description={t("account.security.password.description")}
    >
      <Form {...form}>
        <form
          noValidate
          onSubmit={(event) =>
            void form.handleSubmit(({ currentPassword, password }) => {
              change.mutate(
                { current_password: currentPassword, new_password: password },
                {
                  onSuccess: () => {
                    form.reset(EMPTY);
                  },
                  onError: (error) => {
                    if (isApiErrorCode(error, "invalid_current_password")) {
                      form.setError(
                        "currentPassword",
                        { message: translateApiError(error, t) },
                        { shouldFocus: true },
                      );
                    }
                  },
                },
              );
            })(event)
          }
          className="flex max-w-sm flex-col gap-4"
        >
          {change.isError && !wrongCurrent && (
            <FormAlert message={translateApiError(change.error, t)} />
          )}
          {change.isSuccess && (
            <p role="status" className="text-sm">
              {t("account.security.password.done")}
            </p>
          )}
          <TextField
            control={form.control}
            name="currentPassword"
            type="password"
            label={t("account.security.password.current")}
            autoComplete="current-password"
          />
          <TextField
            control={form.control}
            name="password"
            type="password"
            label={t("auth.fields.newPassword")}
            autoComplete="new-password"
            description={t("auth.passwordHint", { min: PASSWORD_MIN_LENGTH })}
          />
          <TextField
            control={form.control}
            name="confirmPassword"
            type="password"
            label={t("auth.fields.confirmPassword")}
            autoComplete="new-password"
          />
          <div>
            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? t("auth.submitting") : t("account.security.password.submit")}
            </Button>
          </div>
        </form>
      </Form>
    </AccountSection>
  );
}
