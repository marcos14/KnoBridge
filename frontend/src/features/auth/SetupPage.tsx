import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { useRunSetup } from "@/lib/api/setup";

import { AuthCard } from "./AuthCard";
import { FormAlert } from "./FormAlert";
import {
  emailField,
  nameField,
  newPasswordFields,
  PASSWORD_MIN_LENGTH,
  withMatchingPasswords,
} from "./schemas";
import { TextField } from "./TextField";

/** `/setup`: creates the first superadmin of a fresh instance and enters the panel. */
export function SetupPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setup = useRunSetup();
  const schema = useMemo(
    () =>
      withMatchingPasswords(
        z.object({ name: nameField(t), email: emailField(t), ...newPasswordFields(t) }),
        t,
      ),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
  });

  function onSubmit({ name, email, password }: z.infer<typeof schema>) {
    setup.mutate(
      { name, email, password },
      {
        onSuccess: () => {
          void navigate("/", { replace: true });
        },
      },
    );
  }

  return (
    <AuthCard title={t("auth.setup.title")} description={t("auth.setup.description")}>
      <Form {...form}>
        <form
          noValidate
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          className="flex flex-col gap-4"
        >
          {setup.isError && <FormAlert message={translateApiError(setup.error, t)} />}
          <TextField
            control={form.control}
            name="name"
            label={t("auth.fields.name")}
            autoComplete="name"
          />
          <TextField
            control={form.control}
            name="email"
            type="email"
            label={t("auth.fields.email")}
            autoComplete="email"
          />
          <TextField
            control={form.control}
            name="password"
            type="password"
            label={t("auth.fields.password")}
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
          <Button type="submit" disabled={setup.isPending}>
            {setup.isPending ? t("auth.submitting") : t("auth.setup.submit")}
          </Button>
        </form>
      </Form>
    </AuthCard>
  );
}
