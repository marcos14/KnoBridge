import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle } from "lucide-react";
import { type ReactElement, type ReactNode, useId, useMemo, useState } from "react";
import { type Control, useController, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type Assistant, useCreateAssistant, useUpdateAssistant } from "@/lib/api/assistants";
import { useCollections } from "@/lib/api/collections";
import type { Provider } from "@/lib/api/providers";

import {
  ASSISTANT_TONES,
  assistantBody,
  assistantFormDefaults,
  assistantFormSchema,
  type AssistantFormValues,
} from "./assistantForm";
import { webhookApiErrorText } from "./ticketWebhook";
import { TicketWebhookFields } from "./TicketWebhookFields";
import { TicketWebhookPanel } from "./TicketWebhookPanel";

interface AssistantDialogProps {
  workspaceId: string;
  /** The assistant to edit; absent, the dialog creates one. */
  assistant?: Assistant;
  /** Providers of the workspace, offered by the provider picker. */
  providers: readonly Provider[];
  /** The element that opens the dialog (a `Button`). */
  trigger: ReactElement;
  /** Owners and admins generate the webhook secret (a credential); editors only test it. */
  canManageSecret: boolean;
  onSaved: (assistant: Assistant) => void;
}

/**
 * Create or edit an assistant: prompt, provider and model, behavior, the ticket webhook and
 * whether it is active. Editing also offers the webhook secret and the test delivery.
 */
export function AssistantDialog({
  workspaceId,
  assistant,
  providers,
  trigger,
  canManageSecret,
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
    const body = assistantBody(values, assistant);
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
            {save.isError && <FormAlert message={webhookApiErrorText(save.error, t)} />}
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
            <CollectionsField control={form.control} workspaceId={workspaceId} />
            <TextField
              control={form.control}
              name="minSimilarity"
              inputMode="decimal"
              label={t("assistants.form.minSimilarity")}
              description={t("assistants.form.minSimilarityHint")}
            />
            <TextField
              control={form.control}
              name="noSourceMessage"
              rows={3}
              label={t("assistants.form.noSourceMessage")}
              description={t("assistants.form.noSourceMessageHint")}
            />
            <TicketWebhookFields control={form.control} />
            {editing && (
              <TicketWebhookPanel
                workspaceId={workspaceId}
                assistant={assistant}
                canManageSecret={canManageSecret}
              />
            )}
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

/**
 * The collections the assistant answers from, as checkboxes. Mounted only with the dialog open,
 * so the list is fetched when someone edits an assistant, not for every row of the table.
 */
function CollectionsField({ control, workspaceId }: FieldProps & { workspaceId: string }) {
  const { t } = useTranslation();
  const idPrefix = useId();
  const collections = useCollections(workspaceId);
  const { field } = useController({ control, name: "collectionIds" });
  const selected = field.value;

  function toggle(collectionId: string, checked: boolean) {
    field.onChange(
      checked ? [...selected, collectionId] : selected.filter((item) => item !== collectionId),
    );
  }

  let options: ReactNode;
  if (collections.isPending) {
    options = (
      <p role="status" className="text-sm">
        {t("assistants.form.collectionsLoading")}
      </p>
    );
  } else if (collections.isError) {
    options = (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm">
          {t("assistants.form.collectionsLoadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            void collections.refetch();
          }}
        >
          {t("assistants.retry")}
        </Button>
      </div>
    );
  } else if (collections.data.length === 0) {
    options = (
      <p className="text-sm">
        {t("assistants.form.collectionsEmpty")}{" "}
        <Link to={`/w/${workspaceId}/collections`} className="underline underline-offset-4">
          {t("assistants.form.goToCollections")}
        </Link>
      </p>
    );
  } else {
    options = (
      <ul className="flex flex-col gap-2">
        {collections.data.map((collection) => {
          const id = `${idPrefix}-${collection.id}`;
          return (
            <li key={collection.id} className="flex items-start gap-3">
              <Checkbox
                id={id}
                checked={selected.includes(collection.id)}
                onCheckedChange={(checked) => {
                  toggle(collection.id, checked === true);
                }}
              />
              <div className="flex flex-col gap-0.5">
                <Label htmlFor={id}>{collection.name}</Label>
                {collection.description !== "" && (
                  <span className="text-muted-foreground text-xs">{collection.description}</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium">{t("assistants.form.collections")}</legend>
      <p className="text-muted-foreground text-sm">{t("assistants.form.collectionsHint")}</p>
      {options}
      {selected.length === 0 && (
        <p className="flex items-start gap-2 rounded-md border border-amber-500/50 px-3 py-2 text-sm">
          <AlertTriangle aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{t("assistants.form.noCollections")}</span>
        </p>
      )}
    </fieldset>
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
