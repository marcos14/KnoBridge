import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactNode, useId, useMemo } from "react";
import { type Control, type FieldPath, type FieldValues, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogFooter } from "@/components/ui/dialog";
import { Form, FormField, FormItem } from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { KnowledgeItem, KnowledgeItemPatch } from "@/lib/api/knowledge";

import { RULE_CLASSIFICATIONS, RULE_RELEVANCES } from "./knowledgeContent";
import {
  moduleFormSchema,
  type ModuleFormValues,
  moduleFormValues,
  modulePatch,
  ruleFormSchema,
  type RuleFormValues,
  ruleFormValues,
  rulePatch,
} from "./knowledgeForm";

interface EditFormProps {
  item: KnowledgeItem;
  pending: boolean;
  /** The server's refusal, shown above the fields. */
  alert: ReactNode;
  /** `null` when nothing changed. */
  onSubmit: (patch: KnowledgeItemPatch | null) => void;
}

function Footer({ pending }: { pending: boolean }) {
  const { t } = useTranslation();
  return (
    <DialogFooter>
      <DialogClose asChild>
        <Button type="button" variant="outline">
          {t("harness.knowledgeForm.cancel")}
        </Button>
      </DialogClose>
      <Button type="submit" disabled={pending}>
        {pending ? t("auth.submitting") : t("harness.knowledgeForm.submit")}
      </Button>
    </DialogFooter>
  );
}

interface ChoiceProps<Values extends FieldValues> {
  control: Control<Values>;
  name: FieldPath<Values>;
  label: string;
  options: readonly { value: string; label: string }[];
}

/** A labelled group of radio buttons bound to `name`. */
function Choice<Values extends FieldValues>({
  control,
  name,
  label,
  options,
}: ChoiceProps<Values>) {
  const labelId = useId();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <span id={labelId} className="text-sm font-medium">
            {label}
          </span>
          <RadioGroup
            aria-labelledby={labelId}
            value={String(field.value)}
            onValueChange={field.onChange}
            className="flex flex-wrap gap-4"
          >
            {options.map((option) => (
              <div key={option.value} className="flex items-center gap-2">
                <RadioGroupItem value={option.value} id={`${labelId}-${option.value}`} />
                <Label htmlFor={`${labelId}-${option.value}`}>{option.label}</Label>
              </div>
            ))}
          </RadioGroup>
        </FormItem>
      )}
    />
  );
}

/** A rule: title, statement, when, message, how the user solves it, parameters and the seals. */
export function RuleEditForm({ item, pending, alert, onSubmit }: EditFormProps) {
  const { t } = useTranslation();
  const schema = useMemo(() => ruleFormSchema(t), [t]);
  const form = useForm<RuleFormValues>({
    resolver: zodResolver(schema),
    defaultValues: ruleFormValues(item),
  });
  const field = (name: keyof RuleFormValues) => t(`harness.knowledgeForm.${name}`);

  return (
    <Form {...form}>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) =>
          void form.handleSubmit((values) => {
            onSubmit(rulePatch(item, values));
          })(event)
        }
      >
        {alert}
        <TextField control={form.control} name="title" label={field("title")} />
        <TextField control={form.control} name="enunciado" rows={3} label={field("enunciado")} />
        <TextField control={form.control} name="quando" rows={2} label={field("quando")} />
        <TextField control={form.control} name="mensagem" rows={2} label={field("mensagem")} />
        <TextField control={form.control} name="resolucao" rows={3} label={field("resolucao")} />
        <TextField
          control={form.control}
          name="parametros"
          rows={3}
          label={field("parametros")}
          description={t("harness.knowledgeForm.parametrosHint")}
        />
        <Choice
          control={form.control}
          name="classificacao"
          label={field("classificacao")}
          options={RULE_CLASSIFICATIONS.map((value) => ({
            value,
            label: t(`harness.classifications.${value}`),
          }))}
        />
        <Choice
          control={form.control}
          name="relevancia"
          label={field("relevancia")}
          options={RULE_RELEVANCES.map((value) => ({
            value,
            label: t(`harness.relevances.${value}`),
          }))}
        />
        <Footer pending={pending} />
      </form>
    </Form>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-sm font-semibold">{title}</legend>
      {children}
    </fieldset>
  );
}

type EntryGroup = "fluxo_principal" | "mensagens" | "faq" | "duvidas";

/** The form path of one text of an entry, e.g. `mensagens.0.causa`. */
function entryPath<Group extends EntryGroup, Field extends string>(
  group: Group,
  index: number,
  field: Field,
): `${Group}.${number}.${Field}` {
  // `String(index)` widens to `string`; the result is still a numeric index path.
  return `${group}.${String(index)}.${field}` as `${Group}.${number}.${Field}`;
}

/**
 * A module enrichment: title, objective and the text of each step, message, question and open
 * doubt. Entries are not added or removed here, and their evidence markers stay as they are.
 */
export function ModuleEditForm({ item, pending, alert, onSubmit }: EditFormProps) {
  const { t } = useTranslation();
  const schema = useMemo(() => moduleFormSchema(t), [t]);
  const defaults = useMemo(() => moduleFormValues(item), [item]);
  const form = useForm<ModuleFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaults,
  });
  const n = (index: number) => ({ n: index + 1 });

  return (
    <Form {...form}>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) =>
          void form.handleSubmit((values) => {
            onSubmit(modulePatch(item, values));
          })(event)
        }
      >
        {alert}
        <TextField control={form.control} name="title" label={t("harness.knowledgeForm.title")} />
        <TextField
          control={form.control}
          name="objetivo"
          rows={3}
          label={t("harness.knowledgeForm.objetivo")}
        />
        {defaults.fluxo_principal.length > 0 && (
          <Group title={t("harness.knowledgeForm.flow")}>
            {defaults.fluxo_principal.map((_, index) => (
              <TextField
                key={index}
                control={form.control}
                name={entryPath("fluxo_principal", index, "passo")}
                rows={2}
                label={t("harness.knowledgeForm.step", n(index))}
              />
            ))}
          </Group>
        )}
        {defaults.mensagens.length > 0 && (
          <Group title={t("harness.knowledgeForm.messages")}>
            {defaults.mensagens.map((_, index) => (
              <div key={index} className="flex flex-col gap-3">
                <TextField
                  control={form.control}
                  name={entryPath("mensagens", index, "mensagem")}
                  label={t("harness.knowledgeForm.message", n(index))}
                />
                <TextField
                  control={form.control}
                  name={entryPath("mensagens", index, "causa")}
                  rows={2}
                  label={t("harness.knowledgeForm.cause", n(index))}
                />
                <TextField
                  control={form.control}
                  name={entryPath("mensagens", index, "acao")}
                  rows={2}
                  label={t("harness.knowledgeForm.action", n(index))}
                />
              </div>
            ))}
          </Group>
        )}
        {defaults.faq.length > 0 && (
          <Group title={t("harness.knowledgeForm.faq")}>
            {defaults.faq.map((_, index) => (
              <div key={index} className="flex flex-col gap-3">
                <TextField
                  control={form.control}
                  name={entryPath("faq", index, "pergunta")}
                  label={t("harness.knowledgeForm.question", n(index))}
                />
                <TextField
                  control={form.control}
                  name={entryPath("faq", index, "resposta")}
                  rows={2}
                  label={t("harness.knowledgeForm.answer", n(index))}
                />
              </div>
            ))}
          </Group>
        )}
        {defaults.duvidas.length > 0 && (
          <Group title={t("harness.knowledgeForm.doubts")}>
            {defaults.duvidas.map((_, index) => (
              <div key={index} className="flex flex-col gap-3">
                <TextField
                  control={form.control}
                  name={entryPath("duvidas", index, "pergunta")}
                  label={t("harness.knowledgeForm.doubt", n(index))}
                />
                <TextField
                  control={form.control}
                  name={entryPath("duvidas", index, "contexto")}
                  rows={2}
                  label={t("harness.knowledgeForm.context", n(index))}
                />
              </div>
            ))}
          </Group>
        )}
        <Footer pending={pending} />
      </form>
    </Form>
  );
}
