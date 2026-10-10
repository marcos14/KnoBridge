import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";

import {
  nameField,
  newPasswordFields,
  PASSWORD_MIN_LENGTH,
  withMatchingPasswords,
} from "./schemas";
import { TextField } from "./TextField";

export interface InvitationSignupValues {
  name: string;
  password: string;
}

interface InvitationSignupFormProps {
  pending: boolean;
  onSubmit: (values: InvitationSignupValues) => void;
}

/** New account for an invited address: name, password and confirmation (the e-mail is fixed). */
export function InvitationSignupForm({ pending, onSubmit }: InvitationSignupFormProps) {
  const { t } = useTranslation();
  const schema = useMemo(
    () => withMatchingPasswords(z.object({ name: nameField(t), ...newPasswordFields(t) }), t),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", password: "", confirmPassword: "" },
  });

  return (
    <Form {...form}>
      <form
        noValidate
        onSubmit={(event) =>
          void form.handleSubmit(({ name, password }) => {
            onSubmit({ name, password });
          })(event)
        }
        className="flex flex-col gap-4"
      >
        <p className="text-sm">{t("auth.acceptInvitation.createAccount")}</p>
        <TextField
          control={form.control}
          name="name"
          label={t("auth.fields.name")}
          autoComplete="name"
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
        <Button type="submit" disabled={pending}>
          {pending ? t("auth.submitting") : t("auth.acceptInvitation.submitNew")}
        </Button>
      </form>
    </Form>
  );
}
