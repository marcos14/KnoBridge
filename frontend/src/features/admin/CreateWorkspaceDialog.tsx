import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

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
import { Form } from "@/components/ui/form";
import { translateApiError } from "@/i18n/apiErrors";
import { type CreatedWorkspace, useCreateWorkspace } from "@/lib/api/admin";
import { emailField, optionalSlugField, workspaceNameField } from "@/lib/schemas";

interface CreateWorkspaceDialogProps {
  onCreated: (created: CreatedWorkspace) => void;
}

/** "Create workspace" button and its dialog: name, optional slug and the owner's e-mail. */
export function CreateWorkspaceDialog({ onCreated }: CreateWorkspaceDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const create = useCreateWorkspace();
  const schema = useMemo(
    () =>
      z.object({
        name: workspaceNameField(t),
        slug: optionalSlugField(t),
        ownerEmail: emailField(t),
      }),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", slug: "", ownerEmail: "" },
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      form.reset();
      create.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button type="button">{t("admin.workspaces.create.open")}</Button>
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("admin.workspaces.create.title")}</DialogTitle>
          <DialogDescription>{t("admin.workspaces.create.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) =>
              void form.handleSubmit(({ name, slug, ownerEmail }) => {
                create.mutate(
                  { name, slug: slug === "" ? null : slug, owner_email: ownerEmail },
                  {
                    onSuccess: (created) => {
                      setOpen(false);
                      onCreated(created);
                    },
                  },
                );
              })(event)
            }
          >
            {create.isError && <FormAlert message={translateApiError(create.error, t)} />}
            <TextField
              control={form.control}
              name="name"
              label={t("admin.workspaces.create.name")}
              autoComplete="off"
            />
            <TextField
              control={form.control}
              name="slug"
              label={t("admin.workspaces.create.slug")}
              description={t("admin.workspaces.create.slugHint")}
              autoComplete="off"
            />
            <TextField
              control={form.control}
              name="ownerEmail"
              type="email"
              label={t("admin.workspaces.create.ownerEmail")}
              autoComplete="off"
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("admin.workspaces.create.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? t("auth.submitting") : t("admin.workspaces.create.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
