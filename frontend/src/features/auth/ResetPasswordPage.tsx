import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { isApiErrorCode } from "@/lib/api/client";
import { useResetPassword } from "@/lib/api/recovery";

import { AuthCard } from "./AuthCard";
import { FormAlert } from "@/components/FormAlert";
import { FORGOT_PASSWORD_PATH, LOGIN_PATH } from "./redirect";
import { newPasswordFields, PASSWORD_MIN_LENGTH, withMatchingPasswords } from "@/lib/schemas";
import { TextField } from "@/components/TextField";
import { useUrlToken } from "./useUrlToken";

const linkClass = "text-sm underline underline-offset-4";

/** `/reset-password?token=`: chooses a new password from the e-mailed link. */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const token = useUrlToken();
  const reset = useResetPassword();
  const schema = useMemo(() => withMatchingPasswords(z.object(newPasswordFields(t)), t), [t]);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirmPassword: "" },
  });

  if (token === undefined || isApiErrorCode(reset.error, "invalid_token")) {
    return (
      <AuthCard title={t("auth.resetPassword.title")}>
        <p role="alert">{t("auth.resetPassword.invalid")}</p>
        <Link to={FORGOT_PASSWORD_PATH} className={linkClass}>
          {t("auth.resetPassword.requestNew")}
        </Link>
      </AuthCard>
    );
  }

  if (reset.isSuccess) {
    return (
      <AuthCard title={t("auth.resetPassword.title")}>
        <p role="status">{t("auth.resetPassword.done")}</p>
        <Button asChild>
          <Link to={LOGIN_PATH}>{t("auth.resetPassword.goToLogin")}</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t("auth.resetPassword.title")}
      description={t("auth.resetPassword.description")}
    >
      <Form {...form}>
        <form
          noValidate
          onSubmit={(event) =>
            void form.handleSubmit(({ password }) => {
              reset.mutate({ token, password });
            })(event)
          }
          className="flex flex-col gap-4"
        >
          {reset.isError && <FormAlert message={translateApiError(reset.error, t)} />}
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
          <Button type="submit" disabled={reset.isPending}>
            {reset.isPending ? t("auth.submitting") : t("auth.resetPassword.submit")}
          </Button>
        </form>
      </Form>
      <Link to={LOGIN_PATH} className={linkClass}>
        {t("auth.backToLogin")}
      </Link>
    </AuthCard>
  );
}
