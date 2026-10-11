import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FilterSelect } from "@/components/FilterSelect";
import { FormAlert } from "@/components/FormAlert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/i18n/apiErrors";
import { isApiErrorCode } from "@/lib/api/client";
import {
  type HarnessJobBatch,
  type HarnessJobSkipped,
  type HarnessModule,
  useEnqueueHarnessJobs,
} from "@/lib/api/harness";
import type { HarnessExecutor } from "@/lib/api/runners";
import type { Source } from "@/lib/api/sources";

import { HARNESS_EXECUTORS, MODEL_PATTERN, runnerFieldsFromConfig } from "../runnerSourceForm";

/** The executor picked for a batch: the source's default or one of the contract's. */
type ExecutorChoice = "source" | HarnessExecutor;

const SKIP_REASONS = ["already_queued", "module_disabled"] as const;

interface QueuedResult {
  queued: number;
  skipped: HarnessJobSkipped[];
}

interface RunModulesBarProps {
  workspaceId: string;
  source: Source;
  modules: readonly HarnessModule[];
  selected: readonly string[];
  /** Called after the server answers, so the screen can clear the selection. */
  onQueued: () => void;
}

/**
 * Runs the selected modules with the source's executor or another one, optionally with another
 * model. The answer says how many jobs were queued and which modules were skipped, and why.
 */
export function RunModulesBar({
  workspaceId,
  source,
  modules,
  selected,
  onQueued,
}: RunModulesBarProps) {
  const { t } = useTranslation();
  const [executor, setExecutor] = useState<ExecutorChoice>("source");
  const [model, setModel] = useState("");
  const [result, setResult] = useState<QueuedResult | null>(null);
  const enqueue = useEnqueueHarnessJobs(workspaceId, source.id);
  const { defaultExecutor } = runnerFieldsFromConfig(source.config);
  const trimmedModel = model.trim();
  const modelInvalid = trimmedModel !== "" && !MODEL_PATTERN.test(trimmedModel);
  const titleOf = (moduleId: string) =>
    modules.find((module) => module.id === moduleId)?.title ?? moduleId;

  const options = [
    {
      value: "source",
      label: t("harness.run.sourceExecutor", {
        executor: t(`runners.executors.${defaultExecutor}`),
      }),
    },
    ...HARNESS_EXECUTORS.map((name) => ({ value: name, label: t(`runners.executors.${name}`) })),
  ];

  function onRun() {
    if (modelInvalid) {
      return;
    }
    setResult(null);
    const body: HarnessJobBatch = {
      module_ids: [...selected],
      ...(executor === "source" ? {} : { executor }),
      ...(trimmedModel === "" ? {} : { model: trimmedModel }),
    };
    enqueue.mutate(body, {
      onSuccess: ({ jobs, skipped }) => {
        setResult({ queued: jobs.length, skipped });
        onQueued();
      },
    });
  }

  function skipReason(reason: string): string {
    const known = SKIP_REASONS.find((item) => item === reason);
    return known === undefined ? reason : t(`harness.run.skipReasons.${known}`);
  }

  return (
    <section
      aria-label={t("harness.run.label")}
      className="flex flex-col gap-3 rounded-md border p-3"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="harness-run-executor">{t("harness.run.executor")}</Label>
          <FilterSelect
            id="harness-run-executor"
            value={executor}
            options={options}
            className="w-56"
            onValueChange={(value) => {
              setExecutor(value as ExecutorChoice);
            }}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="harness-run-model">{t("harness.run.model")}</Label>
          <Input
            id="harness-run-model"
            className="w-64"
            value={model}
            aria-invalid={modelInvalid}
            aria-describedby="harness-run-model-hint"
            onChange={(event) => {
              setModel(event.target.value);
            }}
          />
        </div>
        <Button
          type="button"
          disabled={selected.length === 0 || modelInvalid || enqueue.isPending}
          onClick={onRun}
        >
          {enqueue.isPending
            ? t("harness.run.running")
            : t("harness.run.submit", { count: selected.length })}
        </Button>
      </div>
      <p id="harness-run-model-hint" className="text-muted-foreground text-xs">
        {modelInvalid ? t("sources.form.validation.modelInvalid") : t("harness.run.modelHint")}
      </p>
      {enqueue.isError && (
        <FormAlert
          message={
            isApiErrorCode(enqueue.error, "source_inactive")
              ? t("harness.run.sourceInactive")
              : translateApiError(enqueue.error, t)
          }
        />
      )}
      {result !== null && (
        <div role="status" className="flex flex-col gap-1 text-sm">
          <p>{t("harness.run.queued", { count: result.queued })}</p>
          {result.skipped.length > 0 && (
            <>
              <p>{t("harness.run.skipped", { count: result.skipped.length })}</p>
              <ul className="list-disc pl-5">
                {result.skipped.map((item) => (
                  <li key={item.module_id}>
                    {t("harness.run.skippedItem", {
                      title: titleOf(item.module_id),
                      reason: skipReason(item.reason),
                    })}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
