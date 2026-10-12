import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { useForgotPassword } from "@/lib/api/recovery";

import { AuthCard } from "./AuthCard";
import { FormAlert } from "@/components/FormAlert";
import { LOGIN_PATH } from "./redirect";
import { emailField } from "@/lib/schemas";
import { TextField } from "@/components/TextField";

/**
 * `/forgot-password`: asks for a reset link. The confirmation is the same whether the address has
 * an account or not, like the API answer.
 */
export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const forgot = useForgotPassword();
  const schema = useMemo(() => z.object({ email: emailField(t) }), [t]);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  const backToLogin = (
    <Link to={LOGIN_PATH} className="text-sm underline underline-offset-4">
      {t("auth.backToLogin")}
    </Link>
  );

  if (forgot.isSuccess) {
    return (
      <AuthCard title={t("auth.forgotPassword.title")}>
        <p role="status">{t("auth.forgotPassword.sent")}</p>
        {backToLogin}
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={t("auth.forgotPassword.title")}
      description={t("auth.forgotPassword.description")}
    >
      <Form {...form}>
        <form
          noValidate
          onSubmit={(event) =>
            void form.handleSubmit((values) => {
              forgot.mutate(values);
            })(event)
          }
          className="flex flex-col gap-4"
        >
          {forgot.isError && <FormAlert message={translateApiError(forgot.error, t)} />}
          <TextField
            control={form.control}
            name="email"
            type="email"
            label={t("auth.fields.email")}
            autoComplete="email"
          />
          <Button type="submit" disabled={forgot.isPending}>
            {forgot.isPending ? t("auth.submitting") : t("auth.forgotPassword.submit")}
          </Button>
        </form>
      </Form>
      {backToLogin}
    </AuthCard>
  );
}
