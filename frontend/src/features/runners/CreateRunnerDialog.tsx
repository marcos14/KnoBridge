import { zodResolver } from "@hookform/resolvers/zod";
import type { TFunction } from "i18next";
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
import { type RunnerCreated, useCreateRunner } from "@/lib/api/runners";

import { CopyButton } from "./CopyButton";
import { runnerSetupCommands } from "./runnerSetup";

/** Limit of the contract (`RunnerCreate.name`). */
export const RUNNER_NAME_MAX_LENGTH = 200;

interface RunnerFormValues {
  name: string;
}

function runnerFormSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, { error: t("runners.form.validation.nameRequired") })
      .max(RUNNER_NAME_MAX_LENGTH, {
        error: t("auth.validation.tooLong", { max: RUNNER_NAME_MAX_LENGTH }),
      }),
  });
}

interface CreateRunnerDialogProps {
  workspaceId: string;
  onCreated: (created: RunnerCreated) => void;
}

/**
 * "Novo runner": asks for the name, then shows the token (returned only by this `POST`) with the
 * commands that install and configure the runner. Closing the dialog drops the token for good.
 */
export function CreateRunnerDialog({ workspaceId, onCreated }: CreateRunnerDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<RunnerCreated | null>(null);
  const create = useCreateRunner(workspaceId);
  const schema = useMemo(() => runnerFormSchema(t), [t]);
  const form = useForm<RunnerFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "" },
  });

  function onOpenChange(next: boolean) {
    setOpen(next);
    // On open and on close: the token never outlives the dialog.
    setCreated(null);
    form.reset({ name: "" });
    create.reset();
  }

  function onSubmit({ name }: RunnerFormValues) {
    create.mutate(name, {
      onSuccess: (result) => {
        setCreated(result);
        onCreated(result);
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button type="button">{t("runners.create")}</Button>
      </DialogTrigger>
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        {created === null ? (
          <>
            <DialogHeader>
              <DialogTitle>{t("runners.form.createTitle")}</DialogTitle>
              <DialogDescription>{t("runners.form.description")}</DialogDescription>
            </DialogHeader>
            <Form {...form}>
              <form
                noValidate
                className="flex flex-col gap-4"
                onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
              >
                {create.isError && <FormAlert message={translateApiError(create.error, t)} />}
                <TextField
                  control={form.control}
                  name="name"
                  label={t("runners.form.name")}
                  description={t("runners.form.nameHint")}
                />
                <DialogFooter>
                  <DialogClose asChild>
                    <Button type="button" variant="outline">
                      {t("runners.form.cancel")}
                    </Button>
                  </DialogClose>
                  <Button type="submit" disabled={create.isPending}>
                    {create.isPending ? t("auth.submitting") : t("runners.form.submit")}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </>
        ) : (
          <TokenView created={created} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function TokenView({ created }: { created: RunnerCreated }) {
  const { t } = useTranslation();
  // The panel and the API share the origin (`/v1` is proxied), so this is the runner's server.
  const commands = runnerSetupCommands(window.location.origin, t("runners.token.repoPlaceholder"));

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("runners.token.title", { name: created.runner.name })}</DialogTitle>
        <DialogDescription>{t("runners.token.description")}</DialogDescription>
      </DialogHeader>
      <section aria-labelledby="runner-token-label" className="flex flex-col gap-2">
        <h3 id="runner-token-label" className="text-sm font-medium">
          {t("runners.token.label")}
        </h3>
        <code className="bg-muted rounded-md p-2 text-sm break-all">{created.token}</code>
        <CopyButton text={created.token} label={t("runners.token.copy")} />
      </section>
      <section aria-labelledby="runner-commands-label" className="flex flex-col gap-2">
        <h3 id="runner-commands-label" className="text-sm font-medium">
          {t("runners.token.commandsLabel")}
        </h3>
        <p className="text-muted-foreground text-sm">{t("runners.token.commandsHint")}</p>
        <pre className="bg-muted overflow-x-auto rounded-md p-2 text-sm">
          <code>{commands}</code>
        </pre>
        <CopyButton text={commands} label={t("runners.token.copyCommands")} />
      </section>
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button">{t("runners.token.done")}</Button>
        </DialogClose>
      </DialogFooter>
    </>
  );
}
