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
import type { PushSourceKind } from "@/lib/api/tickets";

import { CARD_STATUSES } from "./cardsSourceForm";
import type { SourceFormValues } from "./sourceForm";
import { TICKET_STATUSES } from "./ticketsSourceForm";

interface PushFieldsProps {
  form: UseFormReturn<SourceFormValues>;
  kind: PushSourceKind;
  /** Editing: a change only applies to items processed afterwards, which the form says. */
  editing: boolean;
}

/**
 * Fields of a source that receives its items by push. Tickets: whether the text is anonymized,
 * whether internal notes are indexed and which statuses are indexed. Cards: anonymized, whether
 * comments are indexed and which statuses. Items reach the source by the API or a file upload, so
 * there is no location.
 */
export function PushFields({ form, kind, editing }: PushFieldsProps) {
  const { t } = useTranslation();
  const statusesLabelId = useId();
  const tickets = kind === "tickets";
  const extra = tickets ? "includeInternalNotes" : "includeComments";

  return (
    <>
      <p className="text-muted-foreground text-sm">
        {t(tickets ? "sources.form.ticketsHint" : "sources.form.cardsHint")}
      </p>
      {(["anonymize", extra] as const).map((name) => (
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
                <FormDescription>
                  {name === "anonymize" && !tickets
                    ? t("sources.form.cardsAnonymizeHint")
                    : t(`sources.form.${name}Hint`)}
                </FormDescription>
              </div>
            </FormItem>
          )}
        />
      ))}
      {tickets ? (
        <FormField
          control={form.control}
          name="statuses"
          render={({ field }) => (
            <StatusGroup
              labelId={statusesLabelId}
              label={t("sources.form.statuses")}
              hint={t("sources.form.statusesHint")}
              options={TICKET_STATUSES.map((status) => ({
                value: status,
                label: t(`tickets.status.${status}`),
              }))}
              selected={field.value}
              onChange={(values) => {
                field.onChange(TICKET_STATUSES.filter((status) => values.includes(status)));
              }}
            />
          )}
        />
      ) : (
        <FormField
          control={form.control}
          name="cardStatuses"
          render={({ field }) => (
            <StatusGroup
              labelId={statusesLabelId}
              label={t("sources.form.cardStatuses")}
              hint={t("sources.form.cardStatusesHint")}
              options={CARD_STATUSES.map((status) => ({
                value: status,
                label: t(`cards.status.${status}`),
              }))}
              selected={field.value}
              onChange={(values) => {
                field.onChange(CARD_STATUSES.filter((status) => values.includes(status)));
              }}
            />
          )}
        />
      )}
      {editing && (
        <p className="text-sm">
          {t(tickets ? "sources.form.ticketsChangeHint" : "sources.form.cardsChangeHint")}
        </p>
      )}
    </>
  );
}

interface StatusGroupProps {
  labelId: string;
  label: string;
  hint: string;
  options: readonly { value: string; label: string }[];
  selected: readonly string[];
  onChange: (values: string[]) => void;
}

/** A labelled group of status checkboxes; at least one is required (checked by the schema). */
function StatusGroup({ labelId, label, hint, options, selected, onChange }: StatusGroupProps) {
  return (
    <FormItem>
      <span id={labelId} className="text-sm font-medium">
        {label}
      </span>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-4">
        {options.map((option) => {
          const id = `${labelId}-${option.value}`;
          return (
            <div key={option.value} className="flex items-center gap-2">
              <Checkbox
                id={id}
                checked={selected.includes(option.value)}
                onCheckedChange={(checked) => {
                  onChange(
                    checked === true
                      ? [...selected, option.value]
                      : selected.filter((item) => item !== option.value),
                  );
                }}
              />
              <Label htmlFor={id}>{option.label}</Label>
            </div>
          );
        })}
      </div>
      <FormDescription>{hint}</FormDescription>
      <FormMessage />
    </FormItem>
  );
}
