import { delay, http, HttpResponse } from "msw";

import type { components } from "@/lib/api/schema.gen";

const HEALTH_READY = "*/v1/health/ready";

type ReadyResponse = components["schemas"]["ReadyResponse"];

/** GET /v1/health/ready answering 200 (API and database up). */
export const healthReadyOk = http.get(HEALTH_READY, () =>
  HttpResponse.json<ReadyResponse>({ status: "ok", checks: { database: "ok" } }),
);

/** GET /v1/health/ready answering 503 with the standard error shape. */
export const healthReadyUnavailable = http.get(HEALTH_READY, () =>
  HttpResponse.json(
    {
      error: {
        code: "service_unavailable",
        message: "Service is not ready.",
        details: { checks: { database: "error" } },
      },
    },
    { status: 503 },
  ),
);

/** GET /v1/health/ready failing at the network level (API down or unreachable). */
export const healthReadyNetworkError = http.get(HEALTH_READY, () => HttpResponse.error());

/** GET /v1/health/ready that never answers, to observe loading states. */
export const healthReadyPending = http.get(HEALTH_READY, async () => {
  await delay("infinite");
  return HttpResponse.json(null);
});

/** Default handlers: the happy path. Override per test with `server.use(...)`. */
export const handlers = [healthReadyOk];
