import type { HarnessExecutor, Runner, RunnerExecutor } from "@/lib/api/runners";

/** A runner is online while its last contact is this recent (the server's window, 90 s). */
export const ONLINE_WINDOW_MS = 90_000;

export type RunnerStatus = "online" | "offline" | "revoked";

/**
 * Presence of a runner at `now`, from `last_seen_at`: revoked ones never count as online, and a
 * runner that never sent a heartbeat is offline. Computed in the browser so the list ages between
 * refreshes instead of trusting the `online` read at fetch time.
 */
export function runnerStatus(runner: Runner, now: Date): RunnerStatus {
  if (runner.revoked_at !== null) {
    return "revoked";
  }
  if (runner.last_seen_at === null) {
    return "offline";
  }
  const age = now.getTime() - new Date(runner.last_seen_at).getTime();
  return age <= ONLINE_WINDOW_MS ? "online" : "offline";
}

/** Whether a reported executor name is one of the contract's (`claude_code`, `codex`). */
export function isHarnessExecutor(name: string): name is HarnessExecutor {
  return name === "claude_code" || name === "codex";
}

export type ExecutorState = "ready" | "notAuthenticated" | "unavailable";

/** Whether an executor can run jobs: found on the PATH and not known to lack a login. */
export function executorState(executor: RunnerExecutor): ExecutorState {
  if (!executor.available) {
    return "unavailable";
  }
  return executor.authenticated === false ? "notAuthenticated" : "ready";
}
