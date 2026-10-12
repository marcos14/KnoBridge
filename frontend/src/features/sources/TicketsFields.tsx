import { useId } from "react";
import type { UseFormReturn } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Label } from "@/components/ui/label";

import type { SourceFormValues } from "./sourceForm";
import { TICKET_STATUSES } from "./ticketsSourceForm";

interface TicketsFieldsProps {
  form: UseFormReturn<SourceFormValues>;
  /** Editing: a change only applies to tickets processed afterwards, which the form says. */
  editing: boolean;
}

/**
 * Fields of a tickets source: whether internal notes are indexed, whether the text is anonymized
 * and which statuses are indexed. Tickets reach the source by the API or a file upload, so there
 * is no location.
 */
export function TicketsFields({ form, editing }: TicketsFieldsProps) {
  const { t } = useTranslation();
  const statusesLabelId = useId();

  return (
    <>
      <p className="text-muted-foreground text-sm">{t("sources.form.ticketsHint")}</p>
      {(["anonymize", "includeInternalNotes"] as const).map((name) => (
        <FormField
          key={name}
          control={form.control}
          name={name}
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
                <FormLabel>{t(`sources.form.${name}`)}</FormLabel>
                <FormDescription>{t(`sources.form.${name}Hint`)}</FormDescription>
              </div>
            </FormItem>
          )}
        />
      ))}
      <FormField
        control={form.control}
        name="statuses"
        render={({ field }) => (
          <FormItem>
            <span id={statusesLabelId} className="text-sm font-medium">
              {t("sources.form.statuses")}
            </span>
            <div role="group" aria-labelledby={statusesLabelId} className="flex flex-wrap gap-4">
              {TICKET_STATUSES.map((status) => {
                const id = `${statusesLabelId}-${status}`;
                return (
                  <div key={status} className="flex items-center gap-2">
                    <Checkbox
                      id={id}
                      checked={field.value.includes(status)}
                      onCheckedChange={(checked) => {
                        field.onChange(
                          checked === true
                            ? [...field.value, status]
                            : field.value.filter((item) => item !== status),
                        );
                      }}
                    />
                    <Label htmlFor={id}>{t(`tickets.status.${status}`)}</Label>
                  </div>
                );
              })}
            </div>
            <FormDescription>{t("sources.form.statusesHint")}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      {editing && <p className="text-sm">{t("sources.form.ticketsChangeHint")}</p>}
    </>
  );
}
