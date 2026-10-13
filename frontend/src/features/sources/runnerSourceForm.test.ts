import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { COLLECTION_ID, makeRunnerSource, makeSource, RUNNER_ID } from "@/test/factories";

import {
  RUNNER_FORM_DEFAULTS,
  runnerConfig,
  runnerFieldIssues,
  runnerFieldsFromConfig,
  type RunnerFormFields,
} from "./runnerSourceForm";
import {
  sourceChanges,
  sourceFormDefaults,
  sourceFormSchema,
  type SourceFormValues,
  sourceLocation,
} from "./sourceForm";

const t = i18n.t.bind(i18n);

function fields(overrides: Partial<RunnerFormFields> = {}): RunnerFormFields {
  return { ...RUNNER_FORM_DEFAULTS, runnerId: RUNNER_ID, repository: "erp-core", ...overrides };
}

function issuesOf(overrides: Partial<RunnerFormFields>): Record<string, string> {
  return Object.fromEntries(runnerFieldIssues(fields(overrides), t));
}

describe("runnerFieldsFromConfig", () => {
  it("test_runner_fields_read_a_stored_runner_config", () => {
    expect(runnerFieldsFromConfig(makeRunnerSource().config)).toEqual({
      runnerId: RUNNER_ID,
      repository: "erp-core",
      defaultExecutor: "codex",
      claudeModel: "claude-sonnet-4-5",
      codexModel: "",
      budget: "2.5",
      timeout: "900",
      excerptMaxLines: "20",
      autoOnCommit: true,
    });
  });

  it("test_runner_fields_keep_the_defaults_for_other_kinds", () => {
    expect(runnerFieldsFromConfig(makeSource().config)).toEqual(RUNNER_FORM_DEFAULTS);
    expect(runnerFieldsFromConfig({ models: "x" })).toEqual(RUNNER_FORM_DEFAULTS);
  });
});

describe("runnerFieldIssues", () => {
  it("test_runner_fields_accept_valid_values", () => {
    expect(
      issuesOf({ claudeModel: "claude-opus-4:1", budget: "0,1", excerptMaxLines: "0" }),
    ).toEqual({});
    expect(issuesOf({ budget: "100", timeout: "7200", excerptMaxLines: "80" })).toEqual({});
  });

  it("test_runner_fields_require_runner_and_repository", () => {
    expect(issuesOf({ runnerId: "", repository: "" })).toEqual({
      runnerId: "Escolha um runner.",
      repository: "Informe o repositório.",
    });
  });

  it.each(["../erp", "erp/core", "-erp", "a".repeat(65)])(
    "test_runner_fields_reject_repository_%s",
    (repository) => {
      expect(issuesOf({ repository }).repository).toMatch(/nunca um caminho/);
    },
  );

  it("test_runner_fields_reject_models_out_of_the_pattern", () => {
    expect(issuesOf({ claudeModel: "gpt 5", codexModel: "x".repeat(101) })).toEqual({
      claudeModel: "Use até 100 caracteres entre letras, números e . _ : / -",
      codexModel: "Use até 100 caracteres entre letras, números e . _ : / -",
    });
  });

  it.each([["0.05"], ["100.5"], ["abc"], ["1e2"], [""]])(
    "test_runner_fields_reject_budget_%s",
    (budget) => {
      expect(issuesOf({ budget }).budget).toBe("Informe um valor de 0,1 a 100.");
    },
  );

  it.each([["59"], ["7201"], ["90.5"]])("test_runner_fields_reject_timeout_%s", (timeout) => {
    expect(issuesOf({ timeout }).timeout).toBe("Informe um número inteiro de 60 a 7200.");
  });

  it.each([["81"], ["-1"], [""]])("test_runner_fields_reject_excerpt_%s", (excerptMaxLines) => {
    expect(issuesOf({ excerptMaxLines }).excerptMaxLines).toBe(
      "Informe um número inteiro de 0 a 80.",
    );
  });
});

describe("runnerConfig", () => {
  it("test_runner_config_sends_numbers_and_null_models", () => {
    expect(runnerConfig(fields({ budget: "2,5", codexModel: "gpt-5-codex" }))).toEqual({
      runner_id: RUNNER_ID,
      repository: "erp-core",
      default_executor: "claude_code",
      models: { claude_code: null, codex: "gpt-5-codex" },
      budget_usd: 2.5,
      timeout_seconds: 1200,
      auto_on_commit: false,
      excerpt_max_lines: 30,
    });
  });
});

describe("runner source form", () => {
  const schema = sourceFormSchema(t);

  function runnerValues(overrides: Partial<SourceFormValues> = {}): SourceFormValues {
    return {
      ...sourceFormDefaults(undefined, COLLECTION_ID),
      name: "erp-local",
      kind: "runner",
      ...fields(),
      ...overrides,
    };
  }

  it("test_runner_source_form_needs_no_path", () => {
    expect(schema.safeParse(runnerValues()).success).toBe(true);
  });

  it("test_runner_source_form_reports_runner_issues_by_field", () => {
    const result = schema.safeParse(runnerValues({ repository: "a/b" }));

    expect(result.success).toBe(false);
    expect(result.error?.issues.map((item) => item.path.join("."))).toEqual(["repository"]);
  });

  it("test_runner_source_changes_never_send_head_commit", () => {
    const source = makeRunnerSource();
    const changes = sourceChanges(sourceFormDefaults(source, COLLECTION_ID), source.min_level);

    expect(changes.config).not.toHaveProperty("head_commit");
    expect(changes.config).toMatchObject({ runner_id: RUNNER_ID, budget_usd: 2.5 });
  });

  it("test_runner_source_location_is_the_repository", () => {
    expect(sourceLocation(makeRunnerSource())).toBe("erp-core");
    expect(sourceLocation(makeRunnerSource({ config: {} }))).toBe("");
  });
});
