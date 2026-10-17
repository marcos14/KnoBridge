import type { InstanceDashboard, InstanceHealth, ServiceCheck } from "@/lib/api/adminDashboard";
import type { WorkspaceDashboard } from "@/lib/api/dashboard";
import type { StepKey } from "@/lib/firstSteps";

import { OTHER_WORKSPACE_ID, RUN_ID, SOURCE_ID, WORKSPACE_ID } from "./factories";

/** The checklist of `docs/specs/uso-e-custos.md` v0.3, in the API order. */
const CHECKLIST_KEYS: readonly StepKey[] = [
  "provider",
  "collection",
  "source",
  "levels",
  "product",
  "chat",
];

/** The six checklist items in the API order, done when their key is in `done`. */
export function makeChecklist(done: readonly StepKey[] = []): WorkspaceDashboard["checklist"] {
  return CHECKLIST_KEYS.map((key) => ({ key, done: done.includes(key) }));
}

/**
 * Body of `GET .../dashboard` for an owner: 1.234 documents, 2 of 3 sources active, 1 failed run,
 * 12 conversations, 8 👍 and 2 👎 this month, US$ 1,50 of cost, provider and collection done.
 */
export function makeWorkspaceDashboard(
  overrides: Partial<WorkspaceDashboard> = {},
): WorkspaceDashboard {
  return {
    month_start: "2026-10-01T00:00:00Z",
    documents: 1234,
    sources: { total: 3, active: 2 },
    failed_runs: 1,
    conversations_month: 12,
    feedback_month: { up: 8, down: 2 },
    cost_month: { embedding_cost_usd: 0.25, chat_cost_usd: 1.25, cost_usd: 1.5, partial: false },
    checklist: makeChecklist(["provider", "collection"]),
    ...overrides,
  };
}

/**
 * Body of `GET /v1/admin/dashboard`: 3 workspaces (1 suspended), 5 users, one recent failure in
 * Acme Suporte and usage of US$ 2,75 split between two workspaces.
 */
export function makeInstanceDashboard(
  overrides: Partial<InstanceDashboard> = {},
): InstanceDashboard {
  return {
    workspaces: { total: 3, active: 2, suspended: 1 },
    users: { total: 5, suspended: 1, superadmins: 1, active_30d: 4 },
    failed_runs_7d: 2,
    failed_answers_7d: 1,
    recent_failures: [
      {
        run_id: RUN_ID,
        workspace_id: WORKSPACE_ID,
        workspace_name: "Acme Suporte",
        source_id: SOURCE_ID,
        source_name: "erp-core",
        error: "repository unreachable",
        finished_at: "2026-10-10T11:00:00Z",
      },
    ],
    usage: {
      period_start: "2026-09-10T12:00:00Z",
      period_end: "2026-10-10T12:00:00Z",
      embedding_tokens: 1250000,
      embedding_cost_usd: 0.25,
      runs: 14,
      unpriced_runs: 0,
      chat_input_tokens: 98000,
      chat_output_tokens: 12000,
      chat_cost_usd: 2.5,
      answers: 120,
      unpriced_answers: 0,
      chat_searches: 0,
      cost_usd: 2.75,
      by_workspace: [
        {
          workspace_id: WORKSPACE_ID,
          workspace_name: "Acme Suporte",
          cost_usd: 2.5,
          embedding_tokens: 1000000,
          chat_input_tokens: 90000,
          chat_output_tokens: 11000,
        },
        {
          workspace_id: OTHER_WORKSPACE_ID,
          workspace_name: "Beta Help",
          cost_usd: 0.25,
          embedding_tokens: 250000,
          chat_input_tokens: 8000,
          chat_output_tokens: 1000,
        },
      ],
    },
    ...overrides,
  };
}

function check(overrides: Partial<ServiceCheck> = {}): ServiceCheck {
  return { status: "ok", checked_at: "2026-10-10T12:00:00Z", detail: null, ...overrides };
}

/** Body of `GET /v1/admin/health`: everything up unless a service is overridden. */
export function makeInstanceHealth(
  overrides: Partial<Omit<InstanceHealth, "version">> = {},
): InstanceHealth {
  return {
    version: "0.8.0",
    api: check(),
    database: check(),
    temporal: check(),
    worker: check(),
    reranker: {
      ...check({ status: "disabled", detail: "reranker not configured" }),
      model: null,
    },
    ...overrides,
  };
}

/** Health with Temporal down: Temporal in error and the worker unknown. */
export function makeDegradedHealth(): InstanceHealth {
  return makeInstanceHealth({
    temporal: check({ status: "error", detail: "temporal unreachable" }),
    worker: check({ status: "unknown", detail: "temporal down" }),
  });
}
