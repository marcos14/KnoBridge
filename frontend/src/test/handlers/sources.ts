import { http, HttpResponse } from "msw";

import type {
  Run,
  RunDetail,
  RunError,
  RunStatus,
  Source,
  SourceChanges,
  SourceDocument,
  SourceInput,
  SourceTestResult,
} from "@/lib/api/sources";

import {
  makeRun,
  makeRunDetail,
  makeRuns,
  makeSource,
  makeSourceDocuments,
  SOURCE_ID,
} from "../factories";
import { apiErrorResponse } from "./errors";
import { listRecorder, page } from "./page";

const SOURCES = "*/v1/workspaces/:workspaceId/sources";
const SOURCE = "*/v1/workspaces/:workspaceId/sources/:sourceId";
const TEST = "*/v1/workspaces/:workspaceId/sources/:sourceId/test";
const SYNC = "*/v1/workspaces/:workspaceId/sources/:sourceId/sync";
const CANCEL = "*/v1/workspaces/:workspaceId/sources/:sourceId/cancel";
const REINDEX = "*/v1/workspaces/:workspaceId/sources/:sourceId/reindex";
const RUNS = "*/v1/workspaces/:workspaceId/sources/:sourceId/runs";
const DOCUMENTS = "*/v1/workspaces/:workspaceId/sources/:sourceId/documents";
const RUN = "*/v1/workspaces/:workspaceId/runs/:runId";

/** Mutations of a source, for `sourceActionFails`. */
export type SourceAction = "create" | "update" | "delete" | "test" | "sync" | "cancel" | "reindex";

const ACTION_HANDLERS = {
  create: [http.post, SOURCES],
  update: [http.patch, SOURCE],
  delete: [http.delete, SOURCE],
  test: [http.post, TEST],
  sync: [http.post, SYNC],
  cancel: [http.post, CANCEL],
  reindex: [http.post, REINDEX],
} as const;

/** The run a sync or a reindex queues: synthetic id number `n`. */
function queuedRun(sourceId: string, n: number): Run {
  return makeRun({
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    source_id: sourceId,
    status: "queued",
    documents_new: 0,
    chunks_written: 0,
    embedding_tokens: 0,
    cost_usd: null,
    created_at: "2026-10-10T12:00:00Z",
    started_at: null,
    finished_at: null,
  });
}

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

function listOf(request: Request, sources: readonly Source[]) {
  const collectionId = new URL(request.url).searchParams.get("collection_id");
  return page(
    request,
    collectionId === null ? sources : sources.filter((s) => s.collection_id === collectionId),
  );
}

/** One page of `errors` honouring `errors_limit`/`errors_offset` (default 50/0), like the API. */
function runDetailOf(request: Request, run: Run, errors: readonly RunError[]): RunDetail {
  const query = new URL(request.url).searchParams;
  const limit = Number(query.get("errors_limit") ?? "50");
  const offset = Number(query.get("errors_offset") ?? "0");
  return {
    ...run,
    errors: { items: errors.slice(offset, offset + limit), total: errors.length, limit, offset },
  };
}

/** The documents matching `path` (inside the key) and `kind`, like the API with `contains`. */
function documentsOf(request: Request, documents: readonly SourceDocument[]) {
  const query = new URL(request.url).searchParams;
  const path = query.get("path");
  const kind = query.get("kind");
  return page(
    request,
    documents.filter(
      (item) => (path === null || item.key.includes(path)) && (kind === null || item.kind === kind),
    ),
  );
}

/**
 * GET /v1/workspaces/{id}/sources listing `sources` (default: erp-core in Código ERP), filtered by
 * `collection_id` like the API.
 */
export function sourcesAs(sources: Source[] = [makeSource()]) {
  return http.get(SOURCES, ({ request }) => listOf(request, sources));
}

/** GET of the source list recording each query string; `query` matches the name. */
export function sourcesRecorder(sources: Source[] = [makeSource()]) {
  return listRecorder(SOURCES, sources, (item) => [item.name]);
}

/** GET /v1/workspaces/{id}/sources with the default list. */
export const sourcesOk = sourcesAs();

/** GET /v1/workspaces/{id}/sources failing on the server (500). */
export const sourcesServerError = http.get(SOURCES, () => apiErrorResponse(500, "internal_error"));

/** GET of one source failing on the server (500). */
export const sourceServerError = http.get(SOURCE, () => apiErrorResponse(500, "internal_error"));

/** GET of the runs of a source failing on the server (500). */
export const sourceRunsServerError = http.get(RUNS, () => apiErrorResponse(500, "internal_error"));

/** GET of one run failing on the server (500). */
export const runServerError = http.get(RUN, () => apiErrorResponse(500, "internal_error"));

/** GET of the documents of a source failing on the server (500). */
export const sourceDocumentsServerError = http.get(DOCUMENTS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** A source mutation (`action`) refused with `status` and `code`. */
export function sourceActionFails(action: SourceAction, status: number, code: string) {
  const [method, path] = ACTION_HANDLERS[action];
  return method(path, () => apiErrorResponse(status, code));
}

interface SourceStoreOptions {
  /** Runs of each source, newest first (default: `makeRuns()` for erp-core). */
  runs?: Record<string, Run[]>;
  /** Per-document errors of each run (default: none). */
  errors?: Record<string, RunError[]>;
  /** Documents of each source (default: `makeSourceDocuments()` for erp-core). */
  documents?: Record<string, SourceDocument[]>;
  /** Connection test result of each source (default: success). */
  testResults?: Record<string, SourceTestResult>;
}

/**
 * Sources that really change, with the backend's rules: `POST` adds one (409
 * `source_name_taken`), `PATCH` applies the given fields (`schedule_cron: null` clears it), `DELETE`
 * removes it, `sync` queues a run (409 `source_inactive` or `sync_already_running`), `reindex`
 * too (and 409 `source_reindex_unsupported` for tickets; ids in `reindexed`), `cancel`
 * cancels the active one (409 `sync_not_running`). Runs, run errors and documents are served from
 * the options. `finishRun(sourceId, status)` plays the worker ending the active run. `created`,
 * `changes`, `deleted`, `tested`, `synced`, `cancelled`, `documentQueries` and `reads` (the source
 * ids of each `GET` of one source) keep what was asked.
 */
export function sourceStore(initial: Source[] = [makeSource()], options: SourceStoreOptions = {}) {
  let sources = [...initial];
  const runs: Record<string, Run[]> = { [SOURCE_ID]: makeRuns(), ...options.runs };
  const errors: Record<string, RunError[]> = { ...options.errors };
  const documents: Record<string, SourceDocument[]> = {
    [SOURCE_ID]: makeSourceDocuments(),
    ...options.documents,
  };
  const created: SourceInput[] = [];
  const changes: { sourceId: string; body: SourceChanges }[] = [];
  const deleted: string[] = [];
  const tested: string[] = [];
  const synced: string[] = [];
  const cancelled: string[] = [];
  const reindexed: string[] = [];
  const documentQueries: URLSearchParams[] = [];
  const reads: string[] = [];
  const find = (id: unknown) => sources.find((item) => item.id === id);
  const replace = (updated: Source) => {
    sources = sources.map((item) => (item.id === updated.id ? updated : item));
  };
  const setRun = (sourceId: string, run: Run) => {
    const list = (runs[sourceId] ?? []).filter((item) => item.id !== run.id);
    runs[sourceId] = [run, ...list];
    const source = find(sourceId);
    if (source !== undefined) {
      replace({ ...source, last_run: run });
    }
  };
  const activeRun = (source: Source) =>
    source.last_run !== null &&
    (source.last_run.status === "queued" || source.last_run.status === "running")
      ? source.last_run
      : undefined;

  function finishRun(sourceId: string, status: RunStatus = "succeeded") {
    const source = find(sourceId);
    const run = source?.last_run;
    if (run != null) {
      setRun(sourceId, { ...run, status, finished_at: "2026-10-10T12:01:00Z" });
    }
  }

  const handlers = [
    http.get(SOURCES, ({ request }) => listOf(request, sources)),
    http.get(SOURCE, ({ params }) => {
      reads.push(String(params.sourceId));
      const found = find(params.sourceId);
      return found === undefined
        ? apiErrorResponse(404, "source_not_found")
        : HttpResponse.json<Source>(found);
    }),
    http.post(SOURCES, async ({ request }) => {
      const body = (await request.json()) as SourceInput;
      if (sources.some((item) => item.name === body.name)) {
        return apiErrorResponse(409, "source_name_taken");
      }
      const source = makeSource({
        ...body,
        id: `00000000-0000-4000-8000-${String(980 + created.length).padStart(12, "0")}`,
        include_globs: body.include_globs ?? [],
        exclude_globs: body.exclude_globs ?? [],
        schedule_cron: body.schedule_cron ?? null,
        next_run_at: null,
        document_count: 0,
        min_level: body.min_level ?? undefined,
        last_run: null,
      });
      sources = [...sources, source].sort((a, b) => a.name.localeCompare(b.name));
      created.push(body);
      return HttpResponse.json<Source>(source, { status: 201 });
    }),
    http.patch(SOURCE, async ({ params, request }) => {
      const sourceId = String(params.sourceId);
      const body = (await request.json()) as SourceChanges;
      const source = find(sourceId);
      if (source === undefined) {
        return apiErrorResponse(404, "source_not_found");
      }
      const updated: Source = {
        ...source,
        name: body.name ?? source.name,
        config: body.config ?? source.config,
        include_globs: body.include_globs ?? source.include_globs,
        exclude_globs: body.exclude_globs ?? source.exclude_globs,
        schedule_cron: body.schedule_cron === undefined ? source.schedule_cron : body.schedule_cron,
        schedule_enabled: body.schedule_enabled ?? source.schedule_enabled,
        active: body.active ?? source.active,
      };
      replace(updated);
      changes.push({ sourceId, body });
      return HttpResponse.json<Source>(updated);
    }),
    http.delete(SOURCE, ({ params }) => {
      const sourceId = String(params.sourceId);
      sources = sources.filter((item) => item.id !== sourceId);
      deleted.push(sourceId);
      return noContent();
    }),
    http.post(TEST, ({ params }) => {
      const sourceId = String(params.sourceId);
      tested.push(sourceId);
      return HttpResponse.json<SourceTestResult>(
        options.testResults?.[sourceId] ?? { ok: true, error: null },
      );
    }),
    http.post(SYNC, ({ params }) => {
      const sourceId = String(params.sourceId);
      const source = find(sourceId);
      if (source === undefined) {
        return apiErrorResponse(404, "source_not_found");
      }
      if (!source.active) {
        return apiErrorResponse(409, "source_inactive");
      }
      if (activeRun(source) !== undefined) {
        return apiErrorResponse(409, "sync_already_running");
      }
      const run = queuedRun(sourceId, 970 + synced.length);
      setRun(sourceId, run);
      synced.push(sourceId);
      return HttpResponse.json<Run>(run, { status: 202 });
    }),
    http.post(REINDEX, ({ params }) => {
      const sourceId = String(params.sourceId);
      const source = find(sourceId);
      if (source === undefined) {
        return apiErrorResponse(404, "source_not_found");
      }
      if (source.kind === "tickets") {
        return apiErrorResponse(409, "source_reindex_unsupported");
      }
      if (!source.active) {
        return apiErrorResponse(409, "source_inactive");
      }
      if (activeRun(source) !== undefined) {
        return apiErrorResponse(409, "sync_already_running");
      }
      const run = queuedRun(sourceId, 990 + reindexed.length);
      setRun(sourceId, run);
      reindexed.push(sourceId);
      return HttpResponse.json<Run>(run, { status: 202 });
    }),
    http.post(CANCEL, ({ params }) => {
      const sourceId = String(params.sourceId);
      const source = find(sourceId);
      const run = source === undefined ? undefined : activeRun(source);
      if (run === undefined) {
        return apiErrorResponse(409, "sync_not_running");
      }
      cancelled.push(sourceId);
      finishRun(sourceId, "cancelled");
      return HttpResponse.json<Run>({ ...run, status: "cancelled" }, { status: 202 });
    }),
    http.get(RUNS, ({ params, request }) => page(request, runs[String(params.sourceId)] ?? [])),
    http.get(RUN, ({ params, request }) => {
      const runId = String(params.runId);
      const run = Object.values(runs)
        .flat()
        .find((item) => item.id === runId);
      return run === undefined
        ? apiErrorResponse(404, "run_not_found")
        : HttpResponse.json<RunDetail>(runDetailOf(request, run, errors[runId] ?? []));
    }),
    http.get(DOCUMENTS, ({ params, request }) => {
      documentQueries.push(new URL(request.url).searchParams);
      return documentsOf(request, documents[String(params.sourceId)] ?? []);
    }),
  ];
  return {
    handlers,
    created,
    changes,
    deleted,
    tested,
    synced,
    cancelled,
    reindexed,
    documentQueries,
    reads,
    finishRun,
  };
}

/** Stateless defaults: erp-core with its runs (no errors), its documents and mutations that work. */
export const sourcesHandlers = [
  sourcesOk,
  http.get(SOURCE, () => HttpResponse.json<Source>(makeSource())),
  http.post(SOURCES, () => HttpResponse.json<Source>(makeSource(), { status: 201 })),
  http.patch(SOURCE, () => HttpResponse.json<Source>(makeSource())),
  http.delete(SOURCE, noContent),
  http.post(TEST, () => HttpResponse.json<SourceTestResult>({ ok: true, error: null })),
  http.post(SYNC, () => HttpResponse.json<Run>(makeRun({ status: "queued" }), { status: 202 })),
  http.post(CANCEL, () =>
    HttpResponse.json<Run>(makeRun({ status: "cancelled" }), { status: 202 }),
  ),
  http.post(REINDEX, () => HttpResponse.json<Run>(makeRun({ status: "queued" }), { status: 202 })),
  http.get(RUNS, ({ request }) => page(request, makeRuns())),
  http.get(RUN, () => HttpResponse.json<RunDetail>(makeRunDetail())),
  http.get(DOCUMENTS, ({ request }) => documentsOf(request, makeSourceDocuments())),
];
