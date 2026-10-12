/**
 * Tabs of a runner source, in order. A new tab is one more id here, its label in
 * `harness.tabs.<id>` and its content in `RunnerSourceTabs`.
 */
export const RUNNER_SOURCE_TABS = ["modules", "jobs", "knowledge", "indexing"] as const;

export type RunnerSourceTab = (typeof RUNNER_SOURCE_TABS)[number];

/** The tab named by the `tab` query value; unknown or missing is the first one. */
export function parseRunnerSourceTab(value: string | null): RunnerSourceTab {
  return RUNNER_SOURCE_TABS.find((tab) => tab === value) ?? RUNNER_SOURCE_TABS[0];
}
