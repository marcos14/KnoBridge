import { describe, expect, it } from "vitest";

import { fetchAllPages, MAX_PAGE_SIZE } from "./pages";

describe("fetchAllPages", () => {
  it("test_fetch_all_pages_reads_until_total", async () => {
    const rows = Array.from({ length: 250 }, (_, index) => index);
    const queries: { limit: number; offset: number }[] = [];

    const items = await fetchAllPages(({ limit, offset }) => {
      queries.push({ limit, offset });
      return Promise.resolve({ items: rows.slice(offset, offset + limit), total: rows.length });
    });

    expect(items).toEqual(rows);
    expect(queries).toEqual([
      { limit: MAX_PAGE_SIZE, offset: 0 },
      { limit: MAX_PAGE_SIZE, offset: 200 },
    ]);
  });

  it("test_fetch_all_pages_stops_on_empty_page", async () => {
    const items = await fetchAllPages(() => Promise.resolve({ items: [], total: 3 }));

    expect(items).toEqual([]);
  });
});
