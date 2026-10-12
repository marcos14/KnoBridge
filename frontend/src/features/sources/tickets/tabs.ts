/**
 * Tabs of a tickets source, in order. A new tab is one more id here, its label in
 * `tickets.tabs.<id>` and its content in `TicketsSourceTabs`.
 */
export const TICKETS_SOURCE_TABS = ["integration", "upload", "preview", "indexing"] as const;

export type TicketsSourceTab = (typeof TICKETS_SOURCE_TABS)[number];

/** The tab named by the `tab` query value; unknown or missing is the first one. */
export function parseTicketsSourceTab(value: string | null): TicketsSourceTab {
  return TICKETS_SOURCE_TABS.find((tab) => tab === value) ?? TICKETS_SOURCE_TABS[0];
}
