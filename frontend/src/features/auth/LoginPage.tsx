import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { useLogin } from "@/lib/api/auth";

import { AuthCard } from "./AuthCard";
import { FormAlert } from "@/components/FormAlert";
import { FORGOT_PASSWORD_PATH, NEXT_PARAM, safeNextPath } from "./redirect";
import { TextField } from "@/components/TextField";

/** `/login`: e-mail and password; afterwards goes to the validated `?next=` or to the panel. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const login = useLogin();
  const schema = useMemo(
    () =>
      z.object({
        // Only "filled in" here: the account decides, and a format hint would leak nothing useful.
        email: z
          .string()
          .trim()
          .min(1, { error: t("auth.validation.emailRequired") }),
        password: z.string().min(1, { error: t("auth.validation.passwordRequired") }),
      }),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  function onSubmit(values: z.infer<typeof schema>) {
    login.mutate(values, {
      onSuccess: () => {
        void navigate(safeNextPath(searchParams.get(NEXT_PARAM)), { replace: true });
      },
    });
  }

  return (
    <AuthCard title={t("auth.login.title")} description={t("auth.login.description")}>
      <Form {...form}>
        <form
          noValidate
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          className="flex flex-col gap-4"
        >
          {login.isError && <FormAlert message={translateApiError(login.error, t)} />}
          <TextField
            control={form.control}
            name="email"
            type="email"
            label={t("auth.fields.email")}
            autoComplete="username"
          />
          <TextField
            control={form.control}
            name="password"
            type="password"
            label={t("auth.fields.password")}
            autoComplete="current-password"
          />
          <Button type="submit" disabled={login.isPending}>
            {login.isPending ? t("auth.submitting") : t("auth.login.submit")}
          </Button>
        </form>
      </Form>
      <Link to={FORGOT_PASSWORD_PATH} className="text-sm underline underline-offset-4">
        {t("auth.login.forgotPassword")}
      </Link>
    </AuthCard>
  );
}
