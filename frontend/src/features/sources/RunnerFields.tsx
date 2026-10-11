import { type UseFormReturn, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { TextField } from "@/components/TextField";
import { Checkbox } from "@/components/ui/checkbox";
import {
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
import { useClock } from "@/hooks/use-clock";
import { type Runner, useRunners } from "@/lib/api/runners";
import { runnerStatus } from "@/lib/runnerStatus";

import { ChoiceField } from "./ChoiceField";
import {
  BUDGET_MAX_USD,
  BUDGET_MIN_USD,
  EXCERPT_MAX_LINES,
  HARNESS_EXECUTORS,
  TIMEOUT_MAX_SECONDS,
  TIMEOUT_MIN_SECONDS,
} from "./runnerSourceForm";
import type { SourceFormValues } from "./sourceForm";

interface RunnerFieldsProps {
  workspaceId: string;
  form: UseFormReturn<SourceFormValues>;
}

interface Option {
  value: string;
  label: string;
}

/** A labelled select bound to `name`, with its hint and its validation message. */
function SelectField({
  form,
  name,
  label,
  placeholder,
  hint,
  options,
}: {
  form: UseFormReturn<SourceFormValues>;
  name: "runnerId" | "repository";
  label: string;
  placeholder: string;
  hint: string;
  options: readonly Option[];
}) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <Select value={field.value} onValueChange={field.onChange}>
            <FormControl>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={placeholder} />
              </SelectTrigger>
            </FormControl>
            <SelectContent>
              {options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FormDescription>{hint}</FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/**
 * Where a `runner` source lives and how the harness runs there: the runner (revoked ones only
 * when the source already uses one), the repository among those its last heartbeat reported
 * (typed by hand while it is offline or reported none), the default executor, a model per
 * executor, the budget and timeout per job, the excerpt size and the run on every commit.
 */
export function RunnerFields({ workspaceId, form }: RunnerFieldsProps) {
  const { t } = useTranslation();
  const clock = useClock();
  const runners = useRunners(workspaceId);
  const [runnerId, repository] = useWatch({
    control: form.control,
    name: ["runnerId", "repository"],
  });
  const now = clock();
  const all = runners.data ?? [];
  const choices = all.filter((item) => item.revoked_at === null || item.id === runnerId);
  const selected = all.find((item) => item.id === runnerId);

  function runnerLabel(runner: Runner): string {
    const status = runnerStatus(runner, now);
    if (status === "revoked") {
      return t("sources.form.runnerRevoked", { name: runner.name });
    }
    return status === "offline"
      ? t("sources.form.runnerOffline", { name: runner.name })
      : runner.name;
  }

  const served =
    selected !== undefined && runnerStatus(selected, now) === "online"
      ? selected.capabilities.repositories.map((item) => item.name)
      : [];
  // Editing a source whose repository the runner no longer reports keeps it selectable.
  const repositories =
    repository === "" || served.includes(repository) ? served : [...served, repository];

  return (
    <>
      {runners.isPending ? (
        <p role="status" className="text-sm">
          {t("sources.form.runnersLoading")}
        </p>
      ) : runners.isError ? (
        <p role="alert" className="text-sm">
          {t("sources.form.runnersLoadFailed")}
        </p>
      ) : choices.length === 0 ? (
        <p role="alert" className="text-sm">
          {t("sources.form.noRunners")}
        </p>
      ) : (
        <SelectField
          form={form}
          name="runnerId"
          label={t("sources.form.runner")}
          placeholder={t("sources.form.runnerPlaceholder")}
          hint={t("sources.form.runnerHint")}
          options={choices.map((item) => ({ value: item.id, label: runnerLabel(item) }))}
        />
      )}
      {served.length > 0 ? (
        <SelectField
          form={form}
          name="repository"
          label={t("sources.form.repository")}
          placeholder={t("sources.form.repositoryPlaceholder")}
          hint={t("sources.form.repositoryHint")}
          options={repositories.map((name) => ({ value: name, label: name }))}
        />
      ) : (
        <TextField
          control={form.control}
          name="repository"
          label={t("sources.form.repository")}
          description={t("sources.form.repositoryTypeHint")}
        />
      )}
      <ChoiceField
        form={form}
        name="defaultExecutor"
        label={t("sources.form.defaultExecutor")}
        options={HARNESS_EXECUTORS.map((executor) => ({
          value: executor,
          label: t(`sources.form.executors.${executor}`),
        }))}
      />
      <TextField
        control={form.control}
        name="claudeModel"
        label={t("sources.form.claudeModel")}
        description={t("sources.form.modelHint")}
      />
      <TextField
        control={form.control}
        name="codexModel"
        label={t("sources.form.codexModel")}
        description={t("sources.form.modelHint")}
      />
      <TextField
        control={form.control}
        name="budget"
        inputMode="decimal"
        label={t("sources.form.budget")}
        description={t("sources.form.budgetHint", { min: BUDGET_MIN_USD, max: BUDGET_MAX_USD })}
      />
      <TextField
        control={form.control}
        name="timeout"
        inputMode="numeric"
        label={t("sources.form.timeout")}
        description={t("sources.form.timeoutHint", {
          min: TIMEOUT_MIN_SECONDS,
          max: TIMEOUT_MAX_SECONDS,
        })}
      />
      <TextField
        control={form.control}
        name="excerptMaxLines"
        inputMode="numeric"
        label={t("sources.form.excerptMaxLines")}
        description={t("sources.form.excerptMaxLinesHint", { max: EXCERPT_MAX_LINES })}
      />
      <FormField
        control={form.control}
        name="autoOnCommit"
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
              <FormLabel>{t("sources.form.autoOnCommit")}</FormLabel>
              <FormDescription>{t("sources.form.autoOnCommitHint")}</FormDescription>
            </div>
          </FormItem>
        )}
      />
    </>
  );
}
