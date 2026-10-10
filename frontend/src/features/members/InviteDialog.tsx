import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
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
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/i18n/apiErrors";
import type { Role } from "@/lib/api/auth";
import { type Invitation, useCreateInvite } from "@/lib/api/invites";
import { emailField } from "@/lib/schemas";

import { RoleSelect } from "./RoleSelect";

interface InviteDialogProps {
  workspaceId: string;
  /** Role of the logged-in user: the invitation cannot carry a role above it. */
  actorRole: Role;
  onInvited: (invitation: Invitation) => void;
}

const DEFAULT_ROLE: Role = "editor";

/** "Invite" button and its dialog: e-mail and role of a new member. */
export function InviteDialog({ workspaceId, actorRole, onInvited }: InviteDialogProps) {
  const { t } = useTranslation();
  const roleId = useId();
  const roleHintId = useId();
  const [open, setOpen] = useState(false);
  const createInvite = useCreateInvite(workspaceId);
  const schema = useMemo(
    () =>
      z.object({
        email: emailField(t),
        role: z.enum(["owner", "admin", "editor", "viewer"]),
      }),
    [t],
  );
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: DEFAULT_ROLE },
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      form.reset();
      createInvite.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button type="button">{t("members.invite.open")}</Button>
      </DialogTrigger>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t("members.invite.title")}</DialogTitle>
          <DialogDescription>{t("members.invite.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) =>
              void form.handleSubmit((values) => {
                createInvite.mutate(values, {
                  onSuccess: (invitation) => {
                    setOpen(false);
                    onInvited(invitation);
                  },
                });
              })(event)
            }
          >
            {createInvite.isError && (
              <FormAlert message={translateApiError(createInvite.error, t)} />
            )}
            <TextField
              control={form.control}
              name="email"
              type="email"
              label={t("auth.fields.email")}
              autoComplete="off"
            />
            <div className="flex flex-col gap-2">
              <Label htmlFor={roleId}>{t("members.invite.role")}</Label>
              <Controller
                control={form.control}
                name="role"
                render={({ field }) => (
                  <RoleSelect
                    id={roleId}
                    value={field.value}
                    actorRole={actorRole}
                    describedBy={roleHintId}
                    onChange={field.onChange}
                  />
                )}
              />
              <p id={roleHintId} className="text-muted-foreground text-sm">
                {t("members.invite.roleHint")}
              </p>
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  {t("members.invite.cancel")}
                </Button>
              </DialogClose>
              <Button type="submit" disabled={createInvite.isPending}>
                {createInvite.isPending ? t("auth.submitting") : t("members.invite.submit")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
