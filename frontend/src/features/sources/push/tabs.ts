import type { PushSourceRef } from "@/lib/api/tickets";

/** What the tabs read of the source: id and kind (routes and texts), name and whether active. */
export interface PushSource extends PushSourceRef {
  name: string;
  active: boolean;
}

/**
 * Tabs of a push source (tickets or cards), in order. A new tab is one more id here, its label in
 * `ingest.tabs.<id>` and its content in `PushSourceTabs`.
 */
export const PUSH_SOURCE_TABS = ["integration", "upload", "preview", "indexing"] as const;

export type PushSourceTab = (typeof PUSH_SOURCE_TABS)[number];

/** The tab named by the `tab` query value; unknown or missing is the first one. */
export function parsePushSourceTab(value: string | null): PushSourceTab {
  return PUSH_SOURCE_TABS.find((tab) => tab === value) ?? PUSH_SOURCE_TABS[0];
}
