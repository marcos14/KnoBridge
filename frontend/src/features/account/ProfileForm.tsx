import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { resources } from "@/i18n";
import { translateApiError } from "@/i18n/apiErrors";
import { type Me, useUpdateProfile } from "@/lib/api/auth";
import { languageName } from "@/lib/intl";
import { nameField } from "@/lib/schemas";
import { THEMES } from "@/lib/theme";

import { AccountSection } from "./AccountSection";

interface ProfileFormProps {
  user: Me["user"];
}

/** Languages the interface has, plus the one saved in the profile if it is another. */
function localeOptions(current: string): string[] {
  const available = Object.keys(resources);
  return available.includes(current) ? available : [...available, current];
}

/** Name, language and theme of the logged-in user (`PATCH /v1/me`). */
export function ProfileForm({ user }: ProfileFormProps) {
  const { t, i18n } = useTranslation();
  const themeLabelId = useId();
  const updateProfile = useUpdateProfile();
  const schema = useMemo(
    () => z.object({ name: nameField(t), locale: z.string(), theme: z.enum(THEMES) }),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: user.name, locale: user.locale, theme: user.theme },
  });

  return (
    <AccountSection title={t("account.profile.preferences.title")}>
      <Form {...form}>
        <form
          noValidate
          onSubmit={(event) =>
            void form.handleSubmit((values) => {
              updateProfile.mutate(values, {
                onSuccess: (me) => {
                  form.reset({ name: me.user.name, locale: me.user.locale, theme: me.user.theme });
                },
              });
            })(event)
          }
          className="flex flex-col gap-4"
        >
          {updateProfile.isError && (
            <FormAlert message={translateApiError(updateProfile.error, t)} />
          )}
          {updateProfile.isSuccess && (
            <p role="status" className="text-sm">
              {t("account.profile.preferences.saved")}
            </p>
          )}
          <TextField
            control={form.control}
            name="name"
            label={t("auth.fields.name")}
            autoComplete="name"
          />
          <FormField
            control={form.control}
            name="locale"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t("account.profile.preferences.language")}</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full sm:w-64">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {localeOptions(user.locale).map((locale) => (
                      <SelectItem key={locale} value={locale}>
                        {languageName(locale, i18n.language)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>{t("account.profile.preferences.languageHint")}</FormDescription>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="theme"
            render={({ field }) => (
              <FormItem>
                <span id={themeLabelId} className="text-sm font-medium">
                  {t("account.profile.preferences.theme")}
                </span>
                <RadioGroup
                  aria-labelledby={themeLabelId}
                  value={field.value}
                  onValueChange={field.onChange}
                  className="flex flex-wrap gap-4"
                >
                  {THEMES.map((theme) => (
                    <div key={theme} className="flex items-center gap-2">
                      <RadioGroupItem value={theme} id={`${themeLabelId}-${theme}`} />
                      <Label htmlFor={`${themeLabelId}-${theme}`}>
                        {t(`userMenu.themes.${theme}`)}
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              </FormItem>
            )}
          />
          <div>
            <Button type="submit" disabled={updateProfile.isPending}>
              {updateProfile.isPending
                ? t("account.saving")
                : t("account.profile.preferences.submit")}
            </Button>
          </div>
        </form>
      </Form>
    </AccountSection>
  );
}
