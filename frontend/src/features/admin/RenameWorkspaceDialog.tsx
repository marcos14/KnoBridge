import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

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
import type { AdminWorkspace } from "@/lib/api/admin";
import { workspaceNameField } from "@/lib/schemas";

interface RenameWorkspaceDialogProps {
  workspace: AdminWorkspace;
  disabled: boolean;
  /** Called with the new name; the page sends it and reports the result. */
  onRename: (workspace: AdminWorkspace, name: string) => void;
}

/** "Rename" button of a workspace row and its dialog with the new name. */
export function RenameWorkspaceDialog({
  workspace,
  disabled,
  onRename,
}: RenameWorkspaceDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const schema = useMemo(() => z.object({ name: workspaceNameField(t) }), [t]);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: workspace.name },
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      form.reset({ name: workspace.name });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={t("admin.workspaces.rename.openLabel", { name: workspace.name })}
        >
          {t("admin.workspaces.rename.open")}
        </Button>
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("admin.workspaces.rename.title", { name: workspace.name })}</DialogTitle>
          <DialogDescription>{t("admin.workspaces.rename.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) =>
              void form.handleSubmit(({ name }) => {
                setOpen(false);
                onRename(workspace, name);
              })(event)
            }
          >
            <TextField
              control={form.control}
              name="name"
              label={t("admin.workspaces.rename.name")}
              autoComplete="off"
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("admin.workspaces.rename.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit">{t("admin.workspaces.rename.submit")}</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
