import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useMemo, useState } from "react";
import { Controller, useForm, type UseFormReturn, useWatch } from "react-hook-form";
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
import { type Invitation, type InviteInput, useCreateInvite } from "@/lib/api/invites";
import { useProducts } from "@/lib/api/products";
import { defaultMaxLevel } from "@/lib/responseLevels";
import { emailField } from "@/lib/schemas";

import { DEFAULT_LEVEL, type LevelChoice, MemberLevelSelect } from "./MemberLevelSelect";
import { RoleSelect } from "./RoleSelect";

interface InviteDialogProps {
  workspaceId: string;
  /** Role of the logged-in user: the invitation cannot carry a role above it. */
  actorRole: Role;
  onInvited: (invitation: Invitation) => void;
}

const DEFAULT_ROLE: Role = "editor";

/** Levels chosen per product id; a product left out (or at the default) keeps the role's. */
type LevelChoices = Record<string, LevelChoice>;

interface InviteValues {
  email: string;
  role: Role;
  levels: LevelChoices;
}

/** The invitation's `product_levels`: only the products with a level chosen; none, no field. */
function inviteLevels(levels: LevelChoices): Pick<InviteInput, "product_levels"> {
  const chosen = Object.entries(levels).flatMap(([productId, choice]) =>
    choice === DEFAULT_LEVEL ? [] : [{ product_id: productId, max_level: choice }],
  );
  return chosen.length === 0 ? {} : { product_levels: chosen };
}

/**
 * "Invite" button and its dialog: e-mail and role of a new member and, optionally, their maximum
 * level in each product (blank is the default of the invitation's role).
 */
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
        levels: z.record(z.string(), z.enum([DEFAULT_LEVEL, "end_user", "support", "product_dev"])),
      }),
    [t],
  );
  const form = useForm<InviteValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: DEFAULT_ROLE, levels: {} },
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
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("members.invite.title")}</DialogTitle>
          <DialogDescription>{t("members.invite.description")}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={(event) =>
              void form.handleSubmit(({ email, role, levels }) => {
                createInvite.mutate(
                  { email, role, ...inviteLevels(levels) },
                  {
                    onSuccess: (invitation) => {
                      setOpen(false);
                      onInvited(invitation);
                    },
                  },
                );
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
            {open && <InviteLevels workspaceId={workspaceId} form={form} />}
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

interface InviteLevelsProps {
  workspaceId: string;
  form: UseFormReturn<InviteValues>;
}

/** One level picker per product of the workspace, each starting at the default of the role. */
function InviteLevels({ workspaceId, form }: InviteLevelsProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const products = useProducts(workspaceId);
  const role = useWatch({ control: form.control, name: "role" });

  if (products.isPending) {
    return (
      <p role="status" className="text-sm">
        {t("members.invite.levelsLoading")}
      </p>
    );
  }
  if (products.isError) {
    return <p className="text-sm">{t("members.invite.levelsLoadFailed")}</p>;
  }
  if (products.data.length === 0) {
    return null;
  }
  return (
    <fieldset aria-labelledby={titleId} className="flex flex-col gap-2">
      <legend id={titleId} className="text-sm font-medium">
        {t("members.invite.levels")}
      </legend>
      <p className="text-muted-foreground text-sm">{t("members.invite.levelsHint")}</p>
      {products.data.map((product) => (
        <div key={product.id} className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm">{product.name}</span>
          <Controller
            control={form.control}
            name={`levels.${product.id}`}
            defaultValue={DEFAULT_LEVEL}
            render={({ field }) => (
              <div className="w-full sm:w-64">
                <MemberLevelSelect
                  value={field.value}
                  defaultLevel={defaultMaxLevel(role)}
                  defaultLabel="members.invite.levelDefault"
                  label={t("members.invite.levelLabel", { product: product.name })}
                  onChange={field.onChange}
                />
              </div>
            )}
          />
        </div>
      ))}
    </fieldset>
  );
}
