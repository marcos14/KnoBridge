import { HttpResponse } from "msw";

/** One page of `rows`, honouring `limit` and `offset` like the API (default limit 50). */
export function page(request: Request, rows: readonly unknown[]) {
  const query = new URL(request.url).searchParams;
  const limit = Number(query.get("limit") ?? "50");
  const offset = Number(query.get("offset") ?? "0");
  return HttpResponse.json({
    items: rows.slice(offset, offset + limit),
    total: rows.length,
    limit,
    offset,
  });
}

/** Whether `text` contains the `q` query parameter of `request`, ignoring case (no `q`: true). */
export function matchesQuery(request: Request, ...texts: string[]): boolean {
  const q = new URL(request.url).searchParams.get("q")?.toLowerCase();
  return q === undefined || texts.some((text) => text.toLowerCase().includes(q));
}
