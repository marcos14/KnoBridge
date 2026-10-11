import type {
  HarnessJob,
  HarnessJobDetail,
  HarnessModule,
  HarnessRejection,
} from "@/lib/api/harness";

import { RUNNER_ID, RUNNER_SOURCE_ID } from "./factories";

/** Synthetic ids of the harness modules and jobs of the runner source "erp-local". */
export const MODULE_ID = "00000000-0000-4000-8000-0000000003a1";
export const ROOT_MODULE_ID = "00000000-0000-4000-8000-0000000003a2";
export const DISABLED_MODULE_ID = "00000000-0000-4000-8000-0000000003a3";
export const JOB_ID = "00000000-0000-4000-8000-0000000003b1";
export const RUNNING_JOB_ID = "00000000-0000-4000-8000-0000000003b2";

/** `n`-th synthetic id of a module, job or rejection created by a store. */
export function harnessId(n: number): string {
  return `00000000-0000-4000-8000-${String(3000 + n).padStart(12, "0")}`;
}

/**
 * "src/faturamento", a module suggested by the runner: 12 files, 3400 lines, mapped at commit
 * `bbbbbbb…` by a job that succeeded.
 */
export function makeHarnessModule(overrides: Partial<HarnessModule> = {}): HarnessModule {
  return {
    id: MODULE_ID,
    source_id: RUNNER_SOURCE_ID,
    key: "src-faturamento",
    title: "src/faturamento",
    paths: ["src/faturamento/**"],
    suggested: true,
    enabled: true,
    inventory: { files: 12, lines: 3400, languages: { python: { files: 12, lines: 3400 } } },
    last_commit: "b".repeat(40),
    last_job_status: "succeeded",
    created_at: "2026-10-09T10:00:00Z",
    updated_at: "2026-10-09T10:00:00Z",
    ...overrides,
  };
}

/**
 * The modules of "erp-local", by key: "(raiz)" (manual, four patterns, never ran),
 * "src/faturamento" (suggested) and "src/legado" (switched off, never ran).
 */
export function makeHarnessModules(): HarnessModule[] {
  return [
    makeHarnessModule({
      id: ROOT_MODULE_ID,
      key: "root",
      title: "(raiz)",
      paths: ["*", "!*/**", "docs/**", "scripts/**"],
      suggested: false,
      inventory: { files: 3, lines: 120 },
      last_commit: null,
      last_job_status: null,
    }),
    makeHarnessModule(),
    makeHarnessModule({
      id: DISABLED_MODULE_ID,
      key: "src-legado",
      title: "src/legado",
      paths: ["src/legado/**"],
      enabled: false,
      inventory: { files: 40, lines: 51000 },
      last_commit: null,
      last_job_status: null,
    }),
  ];
}

/**
 * A manual job of "src/faturamento" on Codex with the default model that succeeded in 1 min 35 s,
 * costing US$ 0,42, with 5 items accepted and 2 rejected.
 */
export function makeHarnessJob(overrides: Partial<HarnessJob> = {}): HarnessJob {
  return {
    id: JOB_ID,
    source_id: RUNNER_SOURCE_ID,
    module_id: MODULE_ID,
    module_key: "src-faturamento",
    module_title: "src/faturamento",
    runner_id: RUNNER_ID,
    executor: "codex",
    model: null,
    trigger: "manual",
    status: "succeeded",
    attempts: 1,
    not_before: null,
    lease_expires_at: null,
    commit_sha: "b".repeat(40),
    input_tokens: 12000,
    output_tokens: 3400,
    cost_usd: 0.42,
    duration_ms: 95000,
    items_accepted: 5,
    items_rejected: 2,
    error: null,
    created_at: "2026-10-10T11:00:00Z",
    started_at: "2026-10-10T11:00:05Z",
    finished_at: "2026-10-10T11:01:40Z",
    ...overrides,
  };
}

/** A job of "(raiz)" on Claude Code running for two minutes before `TEST_NOW`, no metrics yet. */
export function makeRunningHarnessJob(overrides: Partial<HarnessJob> = {}): HarnessJob {
  return makeHarnessJob({
    id: RUNNING_JOB_ID,
    module_id: ROOT_MODULE_ID,
    module_key: "root",
    module_title: "(raiz)",
    executor: "claude_code",
    model: "claude-sonnet-4-5",
    status: "running",
    input_tokens: null,
    output_tokens: null,
    cost_usd: null,
    duration_ms: null,
    items_accepted: 0,
    items_rejected: 0,
    created_at: "2026-10-10T11:57:00Z",
    started_at: "2026-10-10T11:58:00Z",
    finished_at: null,
    lease_expires_at: "2026-10-10T12:01:00Z",
    ...overrides,
  });
}

/** One item the verification rejected: a rule citing a file missing from the checkout. */
export function makeHarnessRejection(overrides: Partial<HarnessRejection> = {}): HarnessRejection {
  return {
    id: harnessId(900),
    block: "regras",
    item_index: 0,
    label: "Nota exige CNPJ",
    code: "file_not_found",
    reason: "Arquivo citado não existe no checkout ou não é texto.",
    sources: [
      {
        path: "src/faturamento/nota.py",
        start_line: 10,
        end_line: 24,
        symbol: null,
        code: "file_not_found",
      },
    ],
    created_at: "2026-10-10T11:01:40Z",
    ...overrides,
  };
}

/** The two rejections of the default job: a missing file and a symbol not found. */
export function makeHarnessRejections(): HarnessRejection[] {
  return [
    makeHarnessRejection(),
    makeHarnessRejection({
      id: harnessId(901),
      block: "mensagens",
      item_index: 1,
      label: "Informe o CNPJ",
      code: "symbol_mismatch",
      reason: "Símbolo citado não aparece no intervalo nem na assinatura que o envolve.",
      sources: [
        {
          path: "src/faturamento/msg.py",
          start_line: 3,
          end_line: 3,
          symbol: "avisar",
          code: "symbol_mismatch",
        },
      ],
    }),
  ];
}

/** `GET .../harness-jobs/{id}`: the job with one page of its rejections. */
export function makeHarnessJobDetail(
  job: HarnessJob = makeHarnessJob(),
  rejections: HarnessRejection[] = makeHarnessRejections(),
  page: { limit: number; offset: number } = { limit: 300, offset: 0 },
): HarnessJobDetail {
  return {
    ...job,
    rejections: {
      items: rejections.slice(page.offset, page.offset + page.limit),
      total: rejections.length,
      limit: page.limit,
      offset: page.offset,
    },
  };
}
