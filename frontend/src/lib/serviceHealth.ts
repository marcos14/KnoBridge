/** `detail` texts of `GET /v1/admin/health` (`docs/specs/uso-e-custos.md`) and their i18n keys. */
const DETAIL_KEYS = {
  "database unreachable": "databaseUnreachable",
  "temporal unreachable": "temporalUnreachable",
  "task queue unreadable": "taskQueueUnreadable",
  "no worker polling the task queue": "noWorkerPolling",
  "check timed out": "checkTimedOut",
  "temporal down": "temporalDown",
} as const;

export type ServiceDetailKey = (typeof DETAIL_KEYS)[keyof typeof DETAIL_KEYS];

/** Key of a known health `detail`, or `undefined` for none or an unknown one (shown as is). */
export function serviceDetailKey(detail: string | null): ServiceDetailKey | undefined {
  if (detail === null || !Object.hasOwn(DETAIL_KEYS, detail)) {
    return undefined;
  }
  return DETAIL_KEYS[detail as keyof typeof DETAIL_KEYS];
}
