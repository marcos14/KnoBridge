import { HttpResponse } from "msw";

/** Response in the API's standard error shape (`{"error": {code, message, details}}`). */
export function apiErrorResponse(status: number, code: string, details: unknown = null) {
  return HttpResponse.json(
    { error: { code, message: `Synthetic ${code} error.`, details } },
    { status },
  );
}
