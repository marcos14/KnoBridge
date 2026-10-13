import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactNode, useId, useMemo, useState } from "react";
import { type Control, useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
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
import { Form, FormField, FormItem, FormMessage } from "@/components/ui/form";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type ApiKey,
  type ApiKeyCreated,
  useCreateApiKey,
  useUpdateApiKey,
} from "@/lib/api/apiKeys";
import { useAssistants } from "@/lib/api/assistants";

import { API_KEY_VARIABLE } from "./usageExamples";
import {
  type ApiKeyFormValues,
  apiKeyFormDefaults,
  apiKeyFormSchema,
  toApiKeyChanges,
  toApiKeyInput,
} from "./apiKeyForm";

interface ApiKeyDialogProps {
  workspaceId: string;
  trigger: ReactNode;
  /** The key being edited; without it the dialog creates one. */
  apiKey?: ApiKey;
  /** After a save that closes the dialog (an edit), with the message for the page. */
  onSaved: (message: string) => void;
}

/**
 * Creates a key (name and scope), then shows its secret, returned only by the `POST`, with a
 * copy button; closing the dialog drops the secret for good. With `apiKey`, edits name and scope.
 */
export function ApiKeyDialog({ workspaceId, trigger, apiKey, onSaved }: ApiKeyDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const create = useCreateApiKey(workspaceId);
  const update = useUpdateApiKey(workspaceId);
  const save = apiKey === undefined ? create : update;
  const schema = useMemo(() => apiKeyFormSchema(t), [t]);
  const form = useForm<ApiKeyFormValues>({
    resolver: zodResolver(schema),
    defaultValues: apiKeyFormDefaults(apiKey),
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    // On open and on close: the secret never outlives the dialog.
    setCreated(null);
    form.reset(apiKeyFormDefaults(apiKey));
    create.reset();
    update.reset();
  }

  function onSubmit(values: ApiKeyFormValues) {
    if (apiKey === undefined) {
      create.mutate(toApiKeyInput(values), { onSuccess: setCreated });
      return;
    }
    const changes = toApiKeyChanges(apiKey, values);
    const done = (name: string) => {
      setOpen(false);
      onSaved(t("apiKeys.updated", { name }));
    };
    if (changes === null) {
      done(apiKey.name);
      return;
    }
    update.mutate(
      { apiKeyId: apiKey.id, changes },
      {
        onSuccess: (saved) => {
          done(saved.name);
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        {created === null ? (
          <>
            <DialogHeader>
              <DialogTitle>
                {apiKey === undefined
                  ? t("apiKeys.form.createTitle")
                  : t("apiKeys.form.editTitle", { name: apiKey.name })}
              </DialogTitle>
              <DialogDescription>{t("apiKeys.form.description")}</DialogDescription>
            </DialogHeader>
            <Form {...form}>
              <form
                noValidate
                className="flex flex-col gap-4"
                onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
              >
                {save.isError && <FormAlert message={translateApiError(save.error, t)} />}
                <TextField
                  control={form.control}
                  name="name"
                  label={t("apiKeys.form.name")}
                  description={t("apiKeys.form.nameHint")}
                />
                <ScopeField workspaceId={workspaceId} control={form.control} />
                <DialogFooter>
                  <DialogClose asChild>
                    <Button type="button" variant="outline">
                      {t("apiKeys.form.cancel")}
                    </Button>
                  </DialogClose>
                  <Button type="submit" disabled={save.isPending}>
                    {save.isPending ? t("auth.submitting") : t("apiKeys.form.submit")}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </>
        ) : (
          <SecretView created={created} />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface ScopeFieldProps {
  workspaceId: string;
  control: Control<ApiKeyFormValues>;
}

function ScopeField({ workspaceId, control }: ScopeFieldProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const scope = useWatch({ control, name: "scope" });

  return (
    <fieldset className="flex flex-col gap-2">
      <legend id={labelId} className="text-sm font-medium">
        {t("apiKeys.form.scope")}
      </legend>
      <FormField
        control={control}
        name="scope"
        render={({ field }) => (
          <RadioGroup
            aria-labelledby={labelId}
            value={field.value}
            onValueChange={field.onChange}
            className="flex flex-col gap-2"
          >
            {(["all", "selected"] as const).map((value) => (
              <div key={value} className="flex items-center gap-2">
                <RadioGroupItem value={value} id={`${labelId}-${value}`} />
                <Label htmlFor={`${labelId}-${value}`}>{t(`apiKeys.form.scopes.${value}`)}</Label>
              </div>
            ))}
          </RadioGroup>
        )}
      />
      {scope === "selected" && <AssistantsField workspaceId={workspaceId} control={control} />}
    </fieldset>
  );
}

function AssistantsField({ workspaceId, control }: ScopeFieldProps) {
  const { t } = useTranslation();
  const idPrefix = useId();
  const assistants = useAssistants(workspaceId);

  return (
    <FormField
      control={control}
      name="assistantIds"
      render={({ field }) => {
        const selected = field.value;
        const toggle = (id: string, checked: boolean) => {
          field.onChange(checked ? [...selected, id] : selected.filter((item) => item !== id));
        };
        let options: ReactNode;
        if (assistants.isPending) {
          options = (
            <p role="status" className="text-sm">
              {t("apiKeys.form.assistantsLoading")}
            </p>
          );
        } else if (assistants.isError) {
          options = (
            <p role="alert" className="text-sm">
              {t("apiKeys.form.assistantsLoadFailed")}
            </p>
          );
        } else if (assistants.data.length === 0) {
          options = <p className="text-sm">{t("apiKeys.form.assistantsEmpty")}</p>;
        } else {
          options = (
            <ul aria-label={t("apiKeys.form.assistants")} className="flex flex-col gap-2 pl-6">
              {assistants.data.map((assistant) => {
                const id = `${idPrefix}-${assistant.id}`;
                return (
                  <li key={assistant.id} className="flex items-center gap-3">
                    <Checkbox
                      id={id}
                      checked={selected.includes(assistant.id)}
                      onCheckedChange={(checked) => {
                        toggle(assistant.id, checked === true);
                      }}
                    />
                    <Label htmlFor={id}>
                      {assistant.active
                        ? assistant.name
                        : t("apiKeys.form.inactiveAssistant", { name: assistant.name })}
                    </Label>
                  </li>
                );
              })}
            </ul>
          );
        }
        return (
          <FormItem>
            {options}
            <FormMessage />
          </FormItem>
        );
      }}
    />
  );
}

function SecretView({ created }: { created: ApiKeyCreated }) {
  const { t } = useTranslation();
  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("apiKeys.secret.title", { name: created.api_key.name })}</DialogTitle>
        <DialogDescription>
          {t("apiKeys.secret.description", { variable: API_KEY_VARIABLE })}
        </DialogDescription>
      </DialogHeader>
      <section aria-labelledby="api-key-secret-label" className="flex flex-col gap-2">
        <h3 id="api-key-secret-label" className="text-sm font-medium">
          {t("apiKeys.secret.label")}
        </h3>
        <code className="bg-muted rounded-md p-2 text-sm break-all">{created.key}</code>
        <CopyButton text={created.key} label={t("apiKeys.secret.copy")} />
      </section>
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button">{t("apiKeys.secret.done")}</Button>
        </DialogClose>
      </DialogFooter>
    </>
  );
}
