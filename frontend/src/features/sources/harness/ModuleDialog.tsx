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
} from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import {
  type HarnessModule,
  useCreateHarnessModule,
  useUpdateHarnessModule,
} from "@/lib/api/harness";

import {
  moduleCreateBody,
  moduleFormSchema,
  type ModuleFormValues,
  moduleFormValues,
  moduleUpdateBody,
} from "./moduleForm";

interface ModuleDialogProps {
  workspaceId: string;
  sourceId: string;
  /** The module to edit; without it the dialog creates a manual module. */
  module?: HarnessModule;
  trigger: ReactElement;
  onSaved: (saved: HarnessModule) => void;
}

/**
 * Creates a manual module or edits one: title, key (only on creation, optional), patterns (one
 * per line, gitwildmatch as in a `.gitignore`) and whether it runs. Editing the title or the
 * patterns of a suggested module makes it manual, so the runner's reports stop rewriting it.
 */
export function ModuleDialog({
  workspaceId,
  sourceId,
  module,
  trigger,
  onSaved,
}: ModuleDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const creating = module === undefined;
  const create = useCreateHarnessModule(workspaceId, sourceId);
  const update = useUpdateHarnessModule(workspaceId, sourceId);
  const mutation = creating ? create : update;
  const schema = useMemo(() => moduleFormSchema(t, { creating }), [t, creating]);
  const form = useForm<ModuleFormValues>({
    resolver: zodResolver(schema),
    defaultValues: moduleFormValues(module),
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    form.reset(moduleFormValues(module));
    create.reset();
    update.reset();
  }

  function onDone(saved: HarnessModule) {
    setOpen(false);
    onSaved(saved);
  }

  function onSubmit(values: ModuleFormValues) {
    if (module === undefined) {
      create.mutate(moduleCreateBody(values), { onSuccess: onDone });
    } else {
      update.mutate(
        { moduleId: module.id, changes: moduleUpdateBody(values) },
        { onSuccess: onDone },
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {creating ? t("harness.moduleForm.createTitle") : t("harness.moduleForm.editTitle")}
          </DialogTitle>
          <DialogDescription>
            {creating
              ? t("harness.moduleForm.createDescription")
              : module.suggested
                ? t("harness.moduleForm.editSuggestedDescription")
                : t("harness.moduleForm.editDescription")}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          >
            {mutation.isError && <FormAlert message={translateApiError(mutation.error, t)} />}
            <TextField control={form.control} name="title" label={t("harness.moduleForm.title")} />
            {creating && (
              <TextField
                control={form.control}
                name="key"
                label={t("harness.moduleForm.key")}
                description={t("harness.moduleForm.keyHint")}
              />
            )}
            <TextField
              control={form.control}
              name="paths"
              rows={5}
              label={t("harness.moduleForm.paths")}
              description={t("harness.moduleForm.pathsHint")}
            />
            <FormField
              control={form.control}
              name="enabled"
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
                    <FormLabel>{t("harness.moduleForm.enabled")}</FormLabel>
                    <FormDescription>{t("harness.moduleForm.enabledHint")}</FormDescription>
                  </div>
                </FormItem>
              )}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("harness.moduleForm.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? t("auth.submitting") : t("harness.moduleForm.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
