import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
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
import type { Collection } from "@/lib/api/collections";
import { type Source, useCreateSource, useUpdateSource } from "@/lib/api/sources";

import { LocationFields } from "./LocationFields";
import { ScheduleFields } from "./ScheduleFields";
import {
  sourceChanges,
  sourceFormDefaults,
  sourceFormSchema,
  type SourceFormValues,
  sourceInput,
} from "./sourceForm";

interface SourceDialogProps {
  workspaceId: string;
  /** The source to edit; absent, the dialog creates one. */
  source?: Source;
  collections: readonly Collection[];
  /** The element that opens the dialog (a `Button`). */
  trigger: ReactElement;
  onSaved: (source: Source) => void;
}

/**
 * Create or edit a source: name, collection and kind (fixed once created), where it is read from,
 * globs, schedule and whether it is active. The server validates the config again.
 */
export function SourceDialog({
  workspaceId,
  source,
  collections,
  trigger,
  onSaved,
}: SourceDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const editing = source !== undefined;
  const create = useCreateSource(workspaceId);
  const update = useUpdateSource(workspaceId);
  const save = editing ? update : create;
  const schema = useMemo(() => sourceFormSchema(t), [t]);
  const defaults = () => sourceFormDefaults(source, collections[0]?.id ?? "");
  const form = useForm<SourceFormValues>({
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

  function onSubmit(values: SourceFormValues) {
    const done = {
      onSuccess: (saved: Source) => {
        setOpen(false);
        onSaved(saved);
      },
    };
    if (editing) {
      update.mutate({ sourceId: source.id, changes: sourceChanges(values) }, done);
    } else {
      create.mutate(sourceInput(values), done);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {editing ? t("sources.form.editTitle") : t("sources.form.createTitle")}
          </DialogTitle>
          <DialogDescription>{t("sources.form.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          >
            {save.isError && <FormAlert message={translateApiError(save.error, t)} />}
            <TextField control={form.control} name="name" label={t("sources.form.name")} />
            <FormField
              control={form.control}
              name="collectionId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("sources.form.collection")}</FormLabel>
                  <Select value={field.value} disabled={editing} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t("sources.form.collectionPlaceholder")} />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {collections.map((collection) => (
                        <SelectItem key={collection.id} value={collection.id}>
                          {collection.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {editing && (
                    <FormDescription>{t("sources.form.collectionLockedHint")}</FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
            <LocationFields workspaceId={workspaceId} form={form} editing={editing} />
            <TextField
              control={form.control}
              name="includeGlobs"
              rows={2}
              label={t("sources.form.includeGlobs")}
              description={t("sources.form.includeGlobsHint")}
            />
            <TextField
              control={form.control}
              name="excludeGlobs"
              rows={2}
              label={t("sources.form.excludeGlobs")}
              description={t("sources.form.excludeGlobsHint")}
            />
            <ScheduleFields form={form} />
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
                    <FormLabel>{t("sources.form.active")}</FormLabel>
                    <FormDescription>{t("sources.form.activeHint")}</FormDescription>
                  </div>
                </FormItem>
              )}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("sources.form.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={save.isPending}>
                {save.isPending ? t("auth.submitting") : t("sources.form.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
