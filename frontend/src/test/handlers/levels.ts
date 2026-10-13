import { http, HttpResponse } from "msw";

import type { ResponseLevel, WorkspaceLevel, WorkspaceLevelChanges } from "@/lib/api/levels";

import { makeProviders } from "../factories";
import { makeWorkspaceLevels } from "../levelFactories";
import { apiErrorResponse } from "./errors";

const LEVELS = "*/v1/workspaces/:workspaceId/levels";
const LEVEL = `${LEVELS}/:level`;

/** GET .../levels answering `levels` (default: `makeWorkspaceLevels()`). */
export function workspaceLevelsAs(levels: WorkspaceLevel[] = makeWorkspaceLevels()) {
  return http.get(LEVELS, () => HttpResponse.json({ items: levels }));
}

/** GET .../levels failing on the server (500). */
export const workspaceLevelsServerError = http.get(LEVELS, () =>
  apiErrorResponse(500, "internal_error"),
);

/** PATCH .../levels/{level} refused with `status` and `code`. */
export function updateLevelFails(status: number, code: string) {
  return http.patch(LEVEL, () => apiErrorResponse(status, code));
}

/**
 * Levels that really change, like the backend: `PATCH` applies the given fields
 * (`instructions: null` restores the default text, `provider_id` and `model` null turn the level
 * off) and recomputes `configured`, the provider's name and kind (from `makeProviders()`) and
 * `instructions_is_default`. `changes` keeps each request.
 */
export function levelStore(initial: WorkspaceLevel[] = makeWorkspaceLevels()) {
  let levels = [...initial];
  const changes: { level: ResponseLevel; body: WorkspaceLevelChanges }[] = [];
  const providers = makeProviders();
  const handlers = [
    http.get(LEVELS, () => HttpResponse.json({ items: levels })),
    http.patch(LEVEL, async ({ params, request }) => {
      const level = String(params.level) as ResponseLevel;
      const body = (await request.json()) as WorkspaceLevelChanges;
      const current = levels.find((item) => item.level === level);
      if (current === undefined) {
        return apiErrorResponse(422, "validation_error");
      }
      changes.push({ level, body });
      const providerId = body.provider_id === undefined ? current.provider_id : body.provider_id;
      const provider = providers.find(({ id }) => id === providerId);
      const instructions =
        body.instructions === undefined
          ? current.instructions
          : (body.instructions ?? current.default_instructions);
      const model = body.model === undefined ? current.model : body.model;
      const updated: WorkspaceLevel = {
        ...current,
        provider_id: providerId,
        provider_name: provider?.name ?? null,
        provider_kind: provider?.kind ?? null,
        model,
        temperature: body.temperature ?? current.temperature,
        instructions,
        instructions_is_default:
          body.instructions === undefined
            ? current.instructions_is_default
            : body.instructions === null,
        configured: providerId !== null && model !== null,
        updated_at: "2026-10-13T11:00:00Z",
      };
      levels = levels.map((item) => (item.level === level ? updated : item));
      return HttpResponse.json<WorkspaceLevel>(updated);
    }),
  ];
  return { handlers, changes };
}

export const levelsHandlers = [workspaceLevelsAs()];
