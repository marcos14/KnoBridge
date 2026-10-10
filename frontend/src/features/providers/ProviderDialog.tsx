import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
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
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/i18n/apiErrors";
import { type Provider, useCreateProvider, useUpdateProvider } from "@/lib/api/providers";

import {
  createBody,
  PROVIDER_KINDS,
  providerFormDefaults,
  providerFormSchema,
  type ProviderFormValues,
  updateBody,
} from "./providerForm";

interface ProviderDialogProps {
  workspaceId: string;
  /** The provider to edit; absent, the dialog creates one. */
  provider?: Provider;
  /** The element that opens the dialog (a `Button`). */
  trigger: ReactElement;
  onSaved: (provider: Provider) => void;
}

/**
 * Create or edit an LLM provider credential. The key is typed only here, sent once and dropped
 * from the form when the dialog closes; the screen only ever shows the masked `key_hint`.
 */
export function ProviderDialog({ workspaceId, provider, trigger, onSaved }: ProviderDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const editing = provider !== undefined;
  const create = useCreateProvider(workspaceId);
  const update = useUpdateProvider(workspaceId);
  const save = editing ? update : create;
  const schema = useMemo(() => providerFormSchema(t, editing), [t, editing]);
  const form = useForm<ProviderFormValues>({
    resolver: zodResolver(schema),
    defaultValues: providerFormDefaults(provider),
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    // Reset on open and on close, so a typed key never outlives the dialog.
    form.reset(providerFormDefaults(provider));
    save.reset();
  }

  function onSubmit(values: ProviderFormValues) {
    const done = {
      onSuccess: (saved: Provider) => {
        onOpenChange(false);
        onSaved(saved);
      },
    };
    if (editing) {
      update.mutate({ providerId: provider.id, changes: updateBody(values) }, done);
    } else {
      create.mutate(createBody(values), done);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>
            {editing ? t("providers.form.editTitle") : t("providers.form.createTitle")}
          </DialogTitle>
          <DialogDescription>{t("providers.form.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          >
            {save.isError && <FormAlert message={translateApiError(save.error, t)} />}
            <FormField
              control={form.control}
              name="kind"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("providers.form.kind")}</FormLabel>
                  <Select value={field.value} disabled={editing} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {PROVIDER_KINDS.map((kind) => (
                        <SelectItem key={kind} value={kind}>
                          {t(`providers.kinds.${kind}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {editing && <FormDescription>{t("providers.form.kindLocked")}</FormDescription>}
                </FormItem>
              )}
            />
            <TextField control={form.control} name="name" label={t("providers.form.name")} />
            <TextField
              control={form.control}
              name="baseUrl"
              type="url"
              label={t("providers.form.baseUrl")}
              description={t("providers.form.baseUrlHint")}
            />
            <TextField
              control={form.control}
              name="apiKey"
              type="password"
              autoComplete="off"
              label={editing ? t("providers.form.newApiKey") : t("providers.form.apiKey")}
              description={
                editing ? t("providers.form.apiKeyHint", { hint: provider.key_hint }) : undefined
              }
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("providers.form.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? t("auth.submitting") : t("providers.form.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
