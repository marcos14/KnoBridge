import { http, HttpResponse } from "msw";

import type {
  HarnessJob,
  HarnessJobBatch,
  HarnessJobDetail,
  HarnessJobSkipped,
  HarnessJobStatus,
  HarnessModule,
  HarnessModuleChanges,
  HarnessModuleInput,
  HarnessRejection,
} from "@/lib/api/harness";

import { RUNNER_ID } from "../factories";
import {
  harnessId,
  makeHarnessJob,
  makeHarnessJobDetail,
  makeHarnessModule,
  makeHarnessModules,
  makeRunningHarnessJob,
  RUNNING_JOB_ID,
} from "../harnessFactories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const MODULES = "*/v1/workspaces/:workspaceId/sources/:sourceId/modules";
const MODULE = "*/v1/workspaces/:workspaceId/sources/:sourceId/modules/:moduleId";
const SOURCE_JOBS = "*/v1/workspaces/:workspaceId/sources/:sourceId/harness-jobs";
const JOB = "*/v1/workspaces/:workspaceId/harness-jobs/:jobId";
const CANCEL = "*/v1/workspaces/:workspaceId/harness-jobs/:jobId/cancel";

/** Instant the store writes when a job is created, cancelled or finished. */
const STORE_NOW = "2026-10-10T12:00:00Z";

const ACTIVE: readonly HarnessJobStatus[] = ["queued", "leased", "running", "deferred"];

/** Mutations of modules and jobs, for `harnessActionFails`. */
export type HarnessAction = "createModule" | "updateModule" | "enqueue" | "cancel";

const ACTION_HANDLERS = {
  createModule: [http.post, MODULES],
  updateModule: [http.patch, MODULE],
  enqueue: [http.post, SOURCE_JOBS],
  cancel: [http.post, CANCEL],
} as const;

/** A harness mutation (`action`) refused with `status` and `code`. */
export function harnessActionFails(action: HarnessAction, status: number, code: string) {
  const [method, path] = ACTION_HANDLERS[action];
  return method(path, () => apiErrorResponse(status, code));
}

/** GET .../modules failing on the server (500). */
export const harnessModulesServerError = http.get(MODULES, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET .../harness-jobs failing on the server (500). */
export const harnessJobsServerError = http.get(SOURCE_JOBS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** GET .../harness-jobs/{id} failing on the server (500). */
export const harnessJobServerError = http.get(JOB, () => apiErrorResponse(500, "internal_error"));

/** The server's key for a module created without one: the title as a slug. */
function slug(title: string): string {
  return title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

interface HarnessStoreOptions {
  /** Jobs of the sources, newest first. */
  jobs?: HarnessJob[];
  /** Rejections of each job, by job id. */
  rejections?: Record<string, HarnessRejection[]>;
  /** `skipped` reasons forced on module ids (e.g. a module switched off by someone else). */
  forceSkip?: Record<string, string>;
}

/**
 * Modules and jobs that really change, with the backend's rules. `POST .../modules` creates a
 * manual module (409 `module_key_taken`); `PATCH` edits it (title or patterns make it manual);
 * `POST .../harness-jobs` queues one job per enabled module without an active job and skips the
 * others (`module_disabled`, `already_queued`; 404 `module_not_found`); the detail pages the
 * rejections by `rejections_limit`/`rejections_offset`; cancel answers 409 `job_finished` once a
 * job ended. `finishJob(jobId, status)` plays the runner. `created`, `changes`, `enqueued`,
 * `cancelled`, `moduleReads`, `jobReads` and `rejectionQueries` keep what was asked.
 */
export function harnessStore(
  initial: HarnessModule[] = makeHarnessModules(),
  { jobs: initialJobs = [], rejections = {}, forceSkip = {} }: HarnessStoreOptions = {},
) {
  let modules = [...initial];
  let jobs = [...initialJobs];
  const created: HarnessModuleInput[] = [];
  const changes: { moduleId: string; body: HarnessModuleChanges }[] = [];
  const enqueued: HarnessJobBatch[] = [];
  const cancelled: string[] = [];
  const moduleReads: string[] = [];
  const jobReads: string[] = [];
  const rejectionQueries: string[] = [];

  function setModuleStatus(moduleId: string, status: HarnessJobStatus) {
    modules = modules.map((item) =>
      item.id === moduleId ? { ...item, last_job_status: status } : item,
    );
  }

  function setJob(jobId: string, changes: Partial<HarnessJob>): HarnessJob | undefined {
    const job = jobs.find((item) => item.id === jobId);
    if (job === undefined) {
      return undefined;
    }
    const updated = { ...job, ...changes };
    jobs = jobs.map((item) => (item.id === jobId ? updated : item));
    setModuleStatus(updated.module_id, updated.status);
    return updated;
  }

  const handlers = [
    http.get(MODULES, ({ request }) => {
      moduleReads.push(request.url);
      return page(request, modules);
    }),
    http.post(MODULES, async ({ params, request }) => {
      const body = (await request.json()) as HarnessModuleInput;
      const key = body.key ?? slug(body.title);
      if (modules.some((item) => item.key === key)) {
        return apiErrorResponse(409, "module_key_taken");
      }
      const module: HarnessModule = {
        id: harnessId(created.length + 1),
        source_id: String(params.sourceId),
        key,
        title: body.title,
        paths: body.paths,
        suggested: false,
        enabled: body.enabled,
        inventory: { files: 0, lines: 0, languages: {} },
        last_commit: null,
        last_job_status: null,
        created_at: STORE_NOW,
        updated_at: STORE_NOW,
      };
      modules = [...modules, module].sort((a, b) => a.key.localeCompare(b.key));
      created.push(body);
      return HttpResponse.json<HarnessModule>(module, { status: 201 });
    }),
    http.patch(MODULE, async ({ params, request }) => {
      const moduleId = String(params.moduleId);
      const body = (await request.json()) as HarnessModuleChanges;
      const module = modules.find((item) => item.id === moduleId);
      if (module === undefined) {
        return apiErrorResponse(404, "module_not_found");
      }
      const title = body.title ?? module.title;
      const paths = body.paths ?? module.paths;
      const edited = title !== module.title || paths.join("\n") !== module.paths.join("\n");
      const updated: HarnessModule = {
        ...module,
        title,
        paths,
        enabled: body.enabled ?? module.enabled,
        suggested: module.suggested && !edited,
        updated_at: STORE_NOW,
      };
      modules = modules.map((item) => (item.id === moduleId ? updated : item));
      changes.push({ moduleId, body });
      return HttpResponse.json<HarnessModule>(updated);
    }),
    http.get(SOURCE_JOBS, ({ params, request }) => {
      jobReads.push(request.url);
      return page(
        request,
        jobs.filter((job) => job.source_id === String(params.sourceId)),
      );
    }),
    http.post(SOURCE_JOBS, async ({ request }) => {
      const body = (await request.json()) as HarnessJobBatch;
      const ids = [...new Set(body.module_ids)];
      const picked = modules.filter((item) => ids.includes(item.id));
      const missing = ids.filter((id) => !picked.some((item) => item.id === id));
      if (missing.length > 0) {
        return apiErrorResponse(404, "module_not_found", { module_ids: missing });
      }
      const queued: HarnessJob[] = [];
      const skipped: HarnessJobSkipped[] = [];
      for (const module of picked) {
        const id = module.id;
        const busy = jobs.some((job) => job.module_id === id && ACTIVE.includes(job.status));
        const reason =
          forceSkip[id] ?? (!module.enabled ? "module_disabled" : busy ? "already_queued" : null);
        if (reason !== null) {
          skipped.push({ module_id: id, reason });
          continue;
        }
        const job = makeHarnessJob({
          id: harnessId(100 + enqueued.length * 10 + queued.length),
          source_id: module.source_id,
          module_id: id,
          module_key: module.key,
          module_title: module.title,
          runner_id: RUNNER_ID,
          executor: body.executor ?? "codex",
          model: body.model ?? null,
          status: "queued",
          attempts: 0,
          input_tokens: null,
          output_tokens: null,
          cost_usd: null,
          duration_ms: null,
          items_accepted: 0,
          items_rejected: 0,
          created_at: STORE_NOW,
          started_at: null,
          finished_at: null,
        });
        queued.push(job);
        setModuleStatus(id, "queued");
      }
      jobs = [...queued, ...jobs];
      enqueued.push(body);
      return HttpResponse.json({ jobs: queued, skipped }, { status: 202 });
    }),
    http.get(JOB, ({ params, request }) => {
      const jobId = String(params.jobId);
      const job = jobs.find((item) => item.id === jobId);
      if (job === undefined) {
        return apiErrorResponse(404, "job_not_found");
      }
      const query = new URL(request.url).searchParams;
      rejectionQueries.push(query.toString());
      return HttpResponse.json<HarnessJobDetail>(
        makeHarnessJobDetail(job, rejections[jobId] ?? [], {
          limit: Number(query.get("rejections_limit") ?? "300"),
          offset: Number(query.get("rejections_offset") ?? "0"),
        }),
      );
    }),
    http.post(CANCEL, ({ params }) => {
      const jobId = String(params.jobId);
      const job = jobs.find((item) => item.id === jobId);
      if (job === undefined) {
        return apiErrorResponse(404, "job_not_found");
      }
      if (!ACTIVE.includes(job.status)) {
        return apiErrorResponse(409, "job_finished");
      }
      cancelled.push(jobId);
      return HttpResponse.json<HarnessJob>(
        setJob(jobId, { status: "cancelled", finished_at: STORE_NOW }),
      );
    }),
  ];

  /** Plays the runner: ends the job with `status` (and its module's last status). */
  function finishJob(jobId: string, status: HarnessJobStatus) {
    setJob(jobId, { status, finished_at: STORE_NOW });
  }

  return {
    handlers,
    created,
    changes,
    enqueued,
    cancelled,
    moduleReads,
    jobReads,
    rejectionQueries,
    finishJob,
  };
}

/**
 * Stateless defaults: the modules of erp-local, a running and a finished job of it, the detail of
 * either with no rejections, and mutations that answer without changing anything.
 */
export const harnessHandlers = [
  http.get(MODULES, ({ request }) => page(request, makeHarnessModules())),
  http.get(SOURCE_JOBS, ({ request }) =>
    page(request, [makeRunningHarnessJob(), makeHarnessJob()]),
  ),
  http.get(JOB, ({ params }) =>
    HttpResponse.json<HarnessJobDetail>(
      makeHarnessJobDetail(
        String(params.jobId) === RUNNING_JOB_ID ? makeRunningHarnessJob() : makeHarnessJob(),
        [],
      ),
    ),
  ),
  http.post(MODULES, () => HttpResponse.json<HarnessModule>(makeHarnessModule(), { status: 201 })),
  http.patch(MODULE, () => HttpResponse.json<HarnessModule>(makeHarnessModule())),
  http.post(SOURCE_JOBS, () => HttpResponse.json({ jobs: [], skipped: [] }, { status: 202 })),
  http.post(CANCEL, () => HttpResponse.json<HarnessJob>(makeHarnessJob({ status: "cancelled" }))),
];
