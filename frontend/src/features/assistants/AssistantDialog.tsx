import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement, useMemo, useState } from "react";
import { type Control, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/i18n/apiErrors";
import { type Assistant, useCreateAssistant, useUpdateAssistant } from "@/lib/api/assistants";
import type { Provider } from "@/lib/api/providers";

import {
  ASSISTANT_TONES,
  assistantBody,
  assistantFormDefaults,
  assistantFormSchema,
  type AssistantFormValues,
} from "./assistantForm";

interface AssistantDialogProps {
  workspaceId: string;
  /** The assistant to edit; absent, the dialog creates one. */
  assistant?: Assistant;
  /** Providers of the workspace, offered by the provider picker. */
  providers: readonly Provider[];
  /** The element that opens the dialog (a `Button`). */
  trigger: ReactElement;
  onSaved: (assistant: Assistant) => void;
}

/** Create or edit an assistant: prompt, provider and model, behavior and whether it is active. */
export function AssistantDialog({
  workspaceId,
  assistant,
  providers,
  trigger,
  onSaved,
}: AssistantDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const editing = assistant !== undefined;
  const create = useCreateAssistant(workspaceId);
  const update = useUpdateAssistant(workspaceId);
  const save = editing ? update : create;
  const schema = useMemo(() => assistantFormSchema(t), [t]);
  const defaults = () => assistantFormDefaults(assistant, providers[0]?.id ?? "");
  const form = useForm<AssistantFormValues>({
    resolver: zodResolver(schema),
    defaultValues: defaults(),
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      form.reset(defaults());
      save.reset();
    }
  }

  function onSubmit(values: AssistantFormValues) {
    const body = assistantBody(values);
    const done = {
      onSuccess: (saved: Assistant) => {
        setOpen(false);
        onSaved(saved);
      },
    };
    if (editing) {
      update.mutate({ assistantId: assistant.id, changes: body }, done);
    } else {
      create.mutate(body, done);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {editing ? t("assistants.form.editTitle") : t("assistants.form.createTitle")}
          </DialogTitle>
          <DialogDescription>{t("assistants.form.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          >
            {save.isError && <FormAlert message={translateApiError(save.error, t)} />}
            <TextField control={form.control} name="name" label={t("assistants.form.name")} />
            <TextField
              control={form.control}
              name="description"
              rows={2}
              label={t("assistants.form.summary")}
            />
            <TextField
              control={form.control}
              name="systemPrompt"
              rows={6}
              label={t("assistants.form.systemPrompt")}
              description={t("assistants.form.systemPromptHint")}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <ProviderField control={form.control} providers={providers} />
              <TextField
                control={form.control}
                name="model"
                label={t("assistants.form.model")}
                description={t("assistants.form.modelHint")}
              />
              <TextField
                control={form.control}
                name="temperature"
                inputMode="decimal"
                label={t("assistants.form.temperature")}
                description={t("assistants.form.temperatureHint")}
              />
              <TextField
                control={form.control}
                name="language"
                label={t("assistants.form.language")}
                description={t("assistants.form.languageHint")}
              />
              <ToneField control={form.control} />
            </div>
            <TextField
              control={form.control}
              name="noSourceMessage"
              rows={3}
              label={t("assistants.form.noSourceMessage")}
              description={t("assistants.form.noSourceMessageHint")}
            />
            <FormField
              control={form.control}
              name="active"
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
                    <FormLabel>{t("assistants.form.active")}</FormLabel>
                    <FormDescription>{t("assistants.form.activeHint")}</FormDescription>
                  </div>
                </FormItem>
              )}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("assistants.form.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? t("auth.submitting") : t("assistants.form.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

interface FieldProps {
  control: Control<AssistantFormValues>;
}

function ProviderField({ control, providers }: FieldProps & { providers: readonly Provider[] }) {
  const { t } = useTranslation();
  return (
    <FormField
      control={control}
      name="providerId"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("assistants.form.provider")}</FormLabel>
          <Select value={field.value} onValueChange={field.onChange}>
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t("assistants.form.providerPlaceholder")} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {providers.map((provider) => (
                <SelectItem key={provider.id} value={provider.id}>
                  {provider.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

function ToneField({ control }: FieldProps) {
  const { t } = useTranslation();
  return (
    <FormField
      control={control}
      name="tone"
      render={({ field }) => (
        <FormItem>
          <FormLabel>{t("assistants.form.tone")}</FormLabel>
          <Select value={field.value} onValueChange={field.onChange}>
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {ASSISTANT_TONES.map((tone) => (
                <SelectItem key={tone} value={tone}>
                  {t(`assistants.form.tones.${tone}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormItem>
      )}
    />
  );
}
