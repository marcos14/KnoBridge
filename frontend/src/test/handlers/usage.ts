import { delay, http, HttpResponse } from "msw";

import type { UsageGroup, UsageReport } from "@/lib/api/usage";

import { makeUsageReport, USAGE_CSV } from "../usageFactories";
import { apiErrorResponse } from "./errors";

const REPORT = "*/v1/workspaces/:workspaceId/usage";
const CSV = "*/v1/workspaces/:workspaceId/usage.csv";

/** The grouping a request asked for (`day` when missing or unknown, as a test convenience). */
function requestedGroup(request: Request): UsageGroup {
  const group = new URL(request.url).searchParams.get("group_by");
  const groups: UsageGroup[] = ["source", "collection", "assistant", "channel", "api_key", "model"];
  return groups.find((item) => item === group) ?? "day";
}

/** The CSV attachment, named like the API (`knobridge-uso-<group>-<from>-<to>.csv`). */
function csvResponse(request: Request) {
  const params = new URL(request.url).searchParams;
  const day = (name: string) => (params.get(name) ?? "").slice(0, 10);
  const filename = `knobridge-uso-${requestedGroup(request)}-${day("from")}-${day("to")}.csv`;
  return new HttpResponse(USAGE_CSV, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}

/** GET .../usage answering `report(group)` for the requested grouping (default reports). */
export function usageAs(report: (group: UsageGroup) => UsageReport = makeUsageReport) {
  return http.get(REPORT, ({ request }) =>
    HttpResponse.json<UsageReport>(report(requestedGroup(request))),
  );
}

/**
 * The report and the CSV, keeping the query string of each request (`reportQueries`,
 * `csvQueries`) to assert on the period and grouping the screen sent.
 */
export function usageRecorder(report: (group: UsageGroup) => UsageReport = makeUsageReport) {
  const reportQueries: URLSearchParams[] = [];
  const csvQueries: URLSearchParams[] = [];
  const handlers = [
    http.get(REPORT, ({ request }) => {
      reportQueries.push(new URL(request.url).searchParams);
      return HttpResponse.json<UsageReport>(report(requestedGroup(request)));
    }),
    http.get(CSV, ({ request }) => {
      csvQueries.push(new URL(request.url).searchParams);
      return csvResponse(request);
    }),
  ];
  return { handlers, reportQueries, csvQueries };
}

/** GET .../usage failing with `status` and `code` (e.g. 422 `usage_period_too_long`). */
export function usageFails(status: number, code: string) {
  return http.get(REPORT, () => apiErrorResponse(status, code));
}

/** GET .../usage.csv failing with `status` and `code`. */
export function usageCsvFails(status: number, code: string) {
  return http.get(CSV, () => apiErrorResponse(status, code));
}

/** GET .../usage.csv answering without `Content-Disposition` (the screen names the file). */
export const usageCsvWithoutName = http.get(
  CSV,
  () => new HttpResponse(USAGE_CSV, { headers: { "Content-Type": "text/csv" } }),
);

/** GET .../usage.csv that never answers, to see the export in progress. */
export const usageCsvPending = http.get(CSV, async () => {
  await delay("infinite");
  return new HttpResponse(null);
});

/** Default handlers: the default report of each grouping and its CSV. */
export const usageHandlers = [usageAs(), http.get(CSV, ({ request }) => csvResponse(request))];
