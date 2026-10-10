import { zodResolver } from "@hookform/resolvers/zod";
import { useId, useMemo } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

import { FormAlert } from "@/components/FormAlert";
import { TextField } from "@/components/TextField";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCurrentWorkspace } from "@/hooks/use-current-workspace";
import { translateApiError } from "@/i18n/apiErrors";
import type { UserWorkspace } from "@/lib/api/auth";
import { useRenameWorkspace } from "@/lib/api/workspaces";
import { workspaceNameField } from "@/lib/schemas";

/** `/w/:workspaceId/settings` (owner or admin): the workspace's general data. */
export function WorkspaceSettingsPage() {
  const { t } = useTranslation();
  // The route sits under `RequireWorkspaceRole`, which already checked the membership.
  const { workspace } = useCurrentWorkspace();

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{t("workspaceSettings.title")}</h1>
        <p className="text-muted-foreground text-sm">{t("workspaceSettings.description")}</p>
      </div>
      {/* Keyed by workspace: switching workspaces starts the form over with the other's data. */}
      {workspace !== undefined && <GeneralSection key={workspace.id} workspace={workspace} />}
    </div>
  );
}

function GeneralSection({ workspace }: { workspace: UserWorkspace }) {
  const { t } = useTranslation();
  const titleId = useId();
  const slugId = useId();
  const slugHintId = useId();
  const rename = useRenameWorkspace(workspace.id);
  const schema = useMemo(() => z.object({ name: workspaceNameField(t) }), [t]);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: workspace.name },
  });

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-4 rounded-lg border p-6">
      <h2 id={titleId} className="text-lg font-semibold">
        {t("workspaceSettings.general")}
      </h2>
      <Form {...form}>
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) =>
            void form.handleSubmit(({ name }) => {
              rename.mutate(name, {
                onSuccess: (updated) => {
                  form.reset({ name: updated.name });
                },
              });
            })(event)
          }
        >
          {rename.isError && <FormAlert message={translateApiError(rename.error, t)} />}
          {rename.isSuccess && (
            <p role="status" className="text-sm">
              {t("workspaceSettings.saved")}
            </p>
          )}
          <TextField control={form.control} name="name" label={t("workspaceSettings.name")} />
          <div className="flex flex-col gap-2">
            <Label htmlFor={slugId}>{t("workspaceSettings.slug")}</Label>
            <Input id={slugId} value={workspace.slug} readOnly aria-describedby={slugHintId} />
            <p id={slugHintId} className="text-muted-foreground text-sm">
              {t("workspaceSettings.slugHint")}
            </p>
          </div>
          <div>
            <Button type="submit" disabled={rename.isPending}>
              {rename.isPending ? t("account.saving") : t("workspaceSettings.submit")}
            </Button>
          </div>
        </form>
      </Form>
    </section>
  );
}
