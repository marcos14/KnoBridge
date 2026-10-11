import { http, HttpResponse } from "msw";

import type { Runner, RunnerChanges, RunnerCreated } from "@/lib/api/runners";

import { makeNewRunner, makeRunners, RUNNER_TOKEN } from "../factories";
import { apiErrorResponse } from "./errors";
import { page } from "./page";

const RUNNERS = "*/v1/workspaces/:workspaceId/runners";
const RUNNER = "*/v1/workspaces/:workspaceId/runners/:runnerId";

/** Mutations of a runner, for `runnerActionFails`. */
export type RunnerAction = "create" | "update" | "delete";

const ACTION_HANDLERS = {
  create: [http.post, RUNNERS],
  update: [http.patch, RUNNER],
  delete: [http.delete, RUNNER],
} as const;

/** Instant the store writes in `revoked_at`. */
const REVOKED_AT = "2026-10-10T12:00:00Z";

function noContent() {
  return new HttpResponse(null, { status: 204 });
}

/** GET /v1/workspaces/{id}/runners listing `runners` (default: antigo, notebook-ana, build). */
export function runnersAs(runners: Runner[] = makeRunners()) {
  return http.get(RUNNERS, ({ request }) => page(request, runners));
}

/** GET /v1/workspaces/{id}/runners with the default list. */
export const runnersOk = runnersAs();

/** GET /v1/workspaces/{id}/runners failing on the server (500). */
export const runnersServerError = http.get(RUNNERS, () => apiErrorResponse(500, "internal_error"));

/** A runner mutation (`action`) refused with `status` and `code`. */
export function runnerActionFails(action: RunnerAction, status: number, code: string) {
  const [method, path] = ACTION_HANDLERS[action];
  return method(path, () => apiErrorResponse(status, code));
}

interface RunnerStoreOptions {
  /** Runners some source uses: deleting them answers 409 `runner_in_use`. */
  inUse?: string[];
}

/**
 * Runners that really change, with the backend's rules: `POST` adds one that never sent a
 * heartbeat and returns `RUNNER_TOKEN` (409 `runner_name_taken`), `PATCH` renames and revokes
 * (`revoked: false` on a revoked runner answers 422 `runner_revoked`), `DELETE` removes it (409
 * `runner_in_use` for the ids in `inUse`). `created`, `changes` and `deleted` keep what was asked.
 */
export function runnerStore(
  initial: Runner[] = makeRunners(),
  { inUse = [] }: RunnerStoreOptions = {},
) {
  let runners = [...initial];
  const created: string[] = [];
  const changes: { runnerId: string; body: RunnerChanges }[] = [];
  const deleted: string[] = [];
  const find = (id: string) => runners.find((item) => item.id === id);
  const handlers = [
    http.get(RUNNERS, ({ request }) => page(request, runners)),
    http.post(RUNNERS, async ({ request }) => {
      const { name } = (await request.json()) as { name: string };
      if (runners.some((item) => item.name === name)) {
        return apiErrorResponse(409, "runner_name_taken");
      }
      const runner = makeNewRunner({
        id: `00000000-0000-4000-8000-${String(990 + created.length).padStart(12, "0")}`,
        name,
        token_prefix: "ab12cd34",
      });
      runners = [...runners, runner].sort((a, b) => a.name.localeCompare(b.name));
      created.push(name);
      return HttpResponse.json<RunnerCreated>({ runner, token: RUNNER_TOKEN }, { status: 201 });
    }),
    http.patch(RUNNER, async ({ params, request }) => {
      const runnerId = String(params.runnerId);
      const body = (await request.json()) as RunnerChanges;
      const runner = find(runnerId);
      if (runner === undefined) {
        return apiErrorResponse(404, "runner_not_found");
      }
      if (body.revoked === false && runner.revoked_at !== null) {
        return apiErrorResponse(422, "runner_revoked");
      }
      const revoke = body.revoked === true && runner.revoked_at === null;
      const updated: Runner = {
        ...runner,
        name: body.name ?? runner.name,
        revoked_at: revoke ? REVOKED_AT : runner.revoked_at,
        online: revoke ? false : runner.online,
      };
      runners = runners.map((item) => (item.id === runnerId ? updated : item));
      changes.push({ runnerId, body });
      return HttpResponse.json<Runner>(updated);
    }),
    http.delete(RUNNER, ({ params }) => {
      const runnerId = String(params.runnerId);
      if (find(runnerId) === undefined) {
        return apiErrorResponse(404, "runner_not_found");
      }
      if (inUse.includes(runnerId)) {
        return apiErrorResponse(409, "runner_in_use");
      }
      runners = runners.filter((item) => item.id !== runnerId);
      deleted.push(runnerId);
      return noContent();
    }),
  ];
  return { handlers, created, changes, deleted };
}

/** Stateless defaults: the default list, and mutations that work. */
export const runnersHandlers = [
  runnersOk,
  http.post(RUNNERS, () =>
    HttpResponse.json<RunnerCreated>(
      { runner: makeNewRunner(), token: RUNNER_TOKEN },
      { status: 201 },
    ),
  ),
  http.patch(RUNNER, () => HttpResponse.json<Runner>(makeNewRunner({ revoked_at: REVOKED_AT }))),
  http.delete(RUNNER, noContent),
];
