import type { TFunction } from "i18next";

import type { HarnessExecutor } from "@/lib/api/runners";

/**
 * Rules of a `runner` source config (`RunnerSourceConfig` in `ingestion/source_config.py`,
 * `docs/specs/runner.md`). The config travels as a plain object in the API, like Git and folder.
 */
export const REPOSITORY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
export const MODEL_PATTERN = /^[A-Za-z0-9._:/-]{1,100}$/;
export const BUDGET_MIN_USD = 0.1;
export const BUDGET_MAX_USD = 100;
export const DEFAULT_BUDGET_USD = 5;
export const TIMEOUT_MIN_SECONDS = 60;
export const TIMEOUT_MAX_SECONDS = 7200;
export const DEFAULT_TIMEOUT_SECONDS = 1200;
export const EXCERPT_MAX_LINES = 80;
export const DEFAULT_EXCERPT_MAX_LINES = 30;

export const HARNESS_EXECUTORS = [
  "claude_code",
  "codex",
] as const satisfies readonly HarnessExecutor[];

/** Fields of the source form that only a `runner` source uses; numbers are typed as text. */
export interface RunnerFormFields {
  runnerId: string;
  repository: string;
  defaultExecutor: HarnessExecutor;
  /** Blank: the executor's default model (`null`). */
  claudeModel: string;
  codexModel: string;
  budget: string;
  timeout: string;
  excerptMaxLines: string;
  autoOnCommit: boolean;
}

export const RUNNER_FORM_DEFAULTS: RunnerFormFields = {
  runnerId: "",
  repository: "",
  defaultExecutor: "claude_code",
  claudeModel: "",
  codexModel: "",
  budget: String(DEFAULT_BUDGET_USD),
  timeout: String(DEFAULT_TIMEOUT_SECONDS),
  excerptMaxLines: String(DEFAULT_EXCERPT_MAX_LINES),
  autoOnCommit: false,
};

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberText(value: unknown, fallback: number): string {
  return String(typeof value === "number" ? value : fallback);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** The form fields of a stored config; what is missing (other kinds) keeps the defaults. */
export function runnerFieldsFromConfig(config: Record<string, unknown>): RunnerFormFields {
  const models = isRecord(config.models) ? config.models : {};
  return {
    runnerId: text(config.runner_id),
    repository: text(config.repository),
    defaultExecutor: config.default_executor === "codex" ? "codex" : "claude_code",
    claudeModel: text(models.claude_code),
    codexModel: text(models.codex),
    budget: numberText(config.budget_usd, DEFAULT_BUDGET_USD),
    timeout: numberText(config.timeout_seconds, DEFAULT_TIMEOUT_SECONDS),
    excerptMaxLines: numberText(config.excerpt_max_lines, DEFAULT_EXCERPT_MAX_LINES),
    autoOnCommit: config.auto_on_commit === true,
  };
}

/** A decimal typed with a dot or, as in pt-BR, a comma. */
function parseDecimal(value: string): number | null {
  return /^\d+([.,]\d+)?$/.test(value) ? Number(value.replace(",", ".")) : null;
}

function isWholeNumberIn(value: string, min: number, max: number): boolean {
  return /^\d+$/.test(value) && Number(value) >= min && Number(value) <= max;
}

function isBudget(value: string): boolean {
  const budget = parseDecimal(value);
  return budget !== null && budget >= BUDGET_MIN_USD && budget <= BUDGET_MAX_USD;
}

/** Validation problems of the runner fields, as `[field, message]` (values already trimmed). */
export function runnerFieldIssues(
  values: RunnerFormFields,
  t: TFunction,
): [keyof RunnerFormFields, string][] {
  const issues: [keyof RunnerFormFields, string][] = [];
  if (values.runnerId === "") {
    issues.push(["runnerId", t("sources.form.validation.runnerRequired")]);
  }
  if (values.repository === "") {
    issues.push(["repository", t("sources.form.validation.repositoryRequired")]);
  } else if (!REPOSITORY_PATTERN.test(values.repository)) {
    issues.push(["repository", t("sources.form.validation.repositoryInvalid")]);
  }
  for (const field of ["claudeModel", "codexModel"] as const) {
    if (values[field] !== "" && !MODEL_PATTERN.test(values[field])) {
      issues.push([field, t("sources.form.validation.modelInvalid")]);
    }
  }
  if (!isBudget(values.budget)) {
    issues.push([
      "budget",
      t("sources.form.validation.budgetInvalid", { min: BUDGET_MIN_USD, max: BUDGET_MAX_USD }),
    ]);
  }
  if (!isWholeNumberIn(values.timeout, TIMEOUT_MIN_SECONDS, TIMEOUT_MAX_SECONDS)) {
    issues.push([
      "timeout",
      t("sources.form.validation.timeoutInvalid", {
        min: TIMEOUT_MIN_SECONDS,
        max: TIMEOUT_MAX_SECONDS,
      }),
    ]);
  }
  if (!isWholeNumberIn(values.excerptMaxLines, 0, EXCERPT_MAX_LINES)) {
    issues.push([
      "excerptMaxLines",
      t("sources.form.validation.excerptInvalid", { max: EXCERPT_MAX_LINES }),
    ]);
  }
  return issues;
}

/** `config` of a runner source; `head_commit` is the server's and never sent. */
export function runnerConfig(values: RunnerFormFields): Record<string, unknown> {
  return {
    runner_id: values.runnerId,
    repository: values.repository,
    default_executor: values.defaultExecutor,
    models: {
      claude_code: values.claudeModel === "" ? null : values.claudeModel,
      codex: values.codexModel === "" ? null : values.codexModel,
    },
    budget_usd: parseDecimal(values.budget),
    timeout_seconds: Number(values.timeout),
    auto_on_commit: values.autoOnCommit,
    excerpt_max_lines: Number(values.excerptMaxLines),
  };
}
