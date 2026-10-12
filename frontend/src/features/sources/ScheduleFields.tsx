import { useId } from "react";
import { type UseFormReturn, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";

import { CRON_PRESETS, isCronShape } from "./cron";
import { cronText } from "./format";
import type { SourceFormValues } from "./sourceForm";

/**
 * Schedule of the source: "sincronizar automaticamente", the cron expression with ready-made
 * choices and its reading in words while it has five fields. The server validates the rest.
 */
export function ScheduleFields({ form }: { form: UseFormReturn<SourceFormValues> }) {
  const { t, i18n } = useTranslation();
  const presetsId = useId();
  const cron = useWatch({ control: form.control, name: "cron" }).trim();

  return (
    <fieldset className="flex flex-col gap-3">
      <FormField
        control={form.control}
        name="scheduleEnabled"
        render={({ field }) => (
          <FormItem className="flex flex-row items-start gap-3">
            <FormControl>
              <Checkbox
                checked={field.value}
                onCheckedChange={(checked) => {
                  field.onChange(checked === true);
                }}
              />
            </FormControl>
            <div className="flex flex-col gap-1">
              <FormLabel>{t("sources.form.scheduleEnabled")}</FormLabel>
              <FormDescription>{t("sources.form.scheduleEnabledHint")}</FormDescription>
            </div>
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="cron"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t("sources.form.cron")}</FormLabel>
            <FormControl>
              <Input {...field} className="font-mono" placeholder="0 3 * * *" />
            </FormControl>
            <FormDescription>{t("sources.form.cronHint")}</FormDescription>
            {cron !== "" && isCronShape(cron) && (
              <p className="text-sm" aria-live="polite">
                {cronText(cron, t, i18n.language)}
              </p>
            )}
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="flex flex-col gap-2">
        <span id={presetsId} className="text-sm font-medium">
          {t("sources.form.presetsLabel")}
        </span>
        <div role="group" aria-labelledby={presetsId} className="flex flex-wrap gap-2">
          {CRON_PRESETS.map((preset) => (
            <Button
              key={preset.key}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                form.setValue("cron", preset.cron, { shouldDirty: true, shouldValidate: true });
              }}
            >
              {t(`sources.cron.presets.${preset.key}`)}
            </Button>
          ))}
        </div>
      </div>
    </fieldset>
  );
}
