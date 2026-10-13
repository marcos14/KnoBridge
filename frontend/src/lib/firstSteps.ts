import type { Role } from "./api/auth";
import type { ChecklistKey } from "./api/dashboard";
import { hasRole } from "./roles";

/** Keys of the checklist (`docs/specs/uso-e-custos.md`, v0.3). */
export type StepKey = ChecklistKey;

/** One checklist item as the API sends it. */
export interface StepItem {
  key: StepKey;
  done: boolean;
}

interface StepScreen {
  /** Path below `/w/:workspaceId`. */
  path: string;
  /** Role that can do the step on that screen (`docs/specs/uso-e-custos.md`). */
  minRole: Role;
}

/** Screen where each first step is done, and who can do it. */
const STEP_SCREENS: Record<StepKey, StepScreen> = {
  provider: { path: "providers", minRole: "editor" },
  collection: { path: "collections", minRole: "editor" },
  source: { path: "sources", minRole: "editor" },
  levels: { path: "settings", minRole: "admin" },
  product: { path: "products", minRole: "editor" },
  chat: { path: "chat", minRole: "viewer" },
};

export interface PendingStep {
  key: StepKey;
  /** Link to the step's screen, or `undefined` when `role` cannot do it there. */
  to: string | undefined;
}

/**
 * Steps of the checklist still to do, in the API order, each with the link `role` may follow.
 * Done steps are left out; an empty list means the checklist is complete.
 */
export function pendingSteps(
  checklist: readonly StepItem[],
  workspaceId: string,
  role: Role,
): PendingStep[] {
  return checklist
    .filter(({ done }) => !done)
    .map(({ key }) => {
      const { path, minRole } = STEP_SCREENS[key];
      return { key, to: hasRole(role, minRole) ? `/w/${workspaceId}/${path}` : undefined };
    });
}
