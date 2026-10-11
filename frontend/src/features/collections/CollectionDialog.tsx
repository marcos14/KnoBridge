import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement, useMemo, useState } from "react";
import { useForm, type UseFormReturn } from "react-hook-form";
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
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/i18n/apiErrors";
import { type Collection, useCreateCollection, useUpdateCollection } from "@/lib/api/collections";
import type { Provider } from "@/lib/api/providers";

import {
  collectionChanges,
  collectionFormDefaults,
  collectionFormSchema,
  type CollectionFormValues,
  collectionInput,
  defaultEmbeddingModel,
  isEmbeddingLocked,
  isSuggestedModel,
} from "./collectionForm";

interface CollectionDialogProps {
  workspaceId: string;
  /** The collection to edit; absent, the dialog creates one. */
  collection?: Collection;
  /** Credentials that offer embeddings (Anthropic left out). */
  providers: readonly Provider[];
  /** The element that opens the dialog (a `Button`). */
  trigger: ReactElement;
  onSaved: (collection: Collection) => void;
}

/**
 * Create or edit a collection: name, description, embedding credential and model. With documents
 * already indexed, credential and model are locked (the backend would answer 409).
 */
export function CollectionDialog({
  workspaceId,
  collection,
  providers,
  trigger,
  onSaved,
}: CollectionDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const editing = collection !== undefined;
  const locked = isEmbeddingLocked(collection);
  const create = useCreateCollection(workspaceId);
  const update = useUpdateCollection(workspaceId);
  const save = editing ? update : create;
  const schema = useMemo(() => collectionFormSchema(t), [t]);
  const defaults = () => collectionFormDefaults(collection, providers);
  const form = useForm<CollectionFormValues>({
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

  function onSubmit(values: CollectionFormValues) {
    const done = {
      onSuccess: (saved: Collection) => {
        setOpen(false);
        onSaved(saved);
      },
    };
    if (editing) {
      update.mutate(
        { collectionId: collection.id, changes: collectionChanges(values, locked) },
        done,
      );
    } else {
      create.mutate(collectionInput(values), done);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {editing ? t("collections.form.editTitle") : t("collections.form.createTitle")}
          </DialogTitle>
          <DialogDescription>{t("collections.form.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          >
            {save.isError && <FormAlert message={translateApiError(save.error, t)} />}
            <TextField control={form.control} name="name" label={t("collections.form.name")} />
            <TextField
              control={form.control}
              name="description"
              rows={2}
              label={t("collections.form.summary")}
            />
            {locked && (
              <p className="bg-muted rounded-md px-3 py-2 text-sm">
                {t("collections.form.lockedHint")}
              </p>
            )}
            <EmbeddingFields form={form} providers={providers} locked={locked} />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("collections.form.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? t("auth.submitting") : t("collections.form.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

interface EmbeddingFieldsProps {
  form: UseFormReturn<CollectionFormValues>;
  providers: readonly Provider[];
  locked: boolean;
}

/**
 * Credential and model. Picking another credential swaps a suggested model for the one that
 * credential names (OpenRouter with the vendor prefix, OpenAI without); a typed model stays.
 */
function EmbeddingFields({ form, providers, locked }: EmbeddingFieldsProps) {
  const { t } = useTranslation();

  function onProviderChange(providerId: string, onChange: (value: string) => void) {
    onChange(providerId);
    const model = form.getValues("model");
    if (isSuggestedModel(model)) {
      const kind = providers.find((item) => item.id === providerId)?.kind;
      form.setValue("model", defaultEmbeddingModel(kind));
    }
  }

  return (
    <>
      <FormField
        control={form.control}
        name="providerId"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t("collections.form.provider")}</FormLabel>
            <Select
              value={field.value}
              disabled={locked}
              onValueChange={(value) => {
                onProviderChange(value, field.onChange);
              }}
            >
              <FormControl>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t("collections.form.providerPlaceholder")} />
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
            <FormDescription>{t("collections.form.providerHint")}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="model"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t("collections.form.model")}</FormLabel>
            <FormControl>
              <Input {...field} disabled={locked} />
            </FormControl>
            <FormDescription>{t("collections.form.modelHint")}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
}
