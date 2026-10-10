import { delay, http, HttpResponse } from "msw";

/** POST handler that never answers, to observe a form while it is being sent. */
export function pendingPost(path: string) {
  return http.post(path, async () => {
    await delay("infinite");
    return HttpResponse.json(null);
  });
}

/**
 * POST handler that keeps each JSON body it receives before answering with `respond`, so a test
 * can assert what the screen sent. Install `handler` with `server.use(...)` and read `bodies`.
 */
export function recordingPost(path: string, respond: () => Response) {
  const bodies: unknown[] = [];
  const handler = http.post(path, async ({ request }) => {
    bodies.push(await request.json());
    return respond();
  });
  return { handler, bodies };
}
