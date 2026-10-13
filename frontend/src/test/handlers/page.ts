import { http, HttpResponse } from "msw";

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

/**
 * GET handler of a workspace listing that keeps the query string of each request (`queries`) and
 * answers a page of the `rows` whose `texts` contain the `query` parameter, ignoring case, like the
 * API search. Filters and sort are not applied: tests assert them on `queries`.
 */
export function listRecorder<Row>(
  path: string,
  rows: readonly Row[],
  texts: (row: Row) => string[],
) {
  const queries: URLSearchParams[] = [];
  const handler = http.get(path, ({ request }) => {
    const params = new URL(request.url).searchParams;
    queries.push(params);
    const query = params.get("query")?.toLowerCase();
    const matching =
      query === undefined
        ? rows
        : rows.filter((row) => texts(row).some((text) => text.toLowerCase().includes(query)));
    return page(request, matching);
  });
  return {
    handler,
    queries,
    /** The query string of the last request, without `limit`/`offset`, sorted by key. */
    last: () => {
      const params = new URLSearchParams(queries.at(-1));
      params.delete("limit");
      params.delete("offset");
      params.sort();
      return params.toString();
    },
  };
}
