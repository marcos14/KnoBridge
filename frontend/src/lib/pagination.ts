/** Offset pagination (`limit`/`offset`/`total`), as every listing of the API answers. */

export interface PageRange {
  /** 1-based position of the first row on the page; 0 when there are no rows. */
  from: number;
  /** 1-based position of the last row on the page. */
  to: number;
}

/** Rows shown by the page starting at `offset`, for the "1–20 de 45" label. */
export function pageRange(offset: number, limit: number, total: number): PageRange {
  if (total === 0) {
    return { from: 0, to: 0 };
  }
  return { from: offset + 1, to: Math.min(offset + limit, total) };
}

/**
 * A valid offset for `total` rows: the last page's when `offset` went past the end (the last row
 * of the last page was removed, the search shrank the list).
 */
export function clampOffset(offset: number, limit: number, total: number): number {
  if (offset < total) {
    return offset;
  }
  return Math.max(0, Math.floor((total - 1) / limit) * limit);
}

/** The page of `rows` starting at `offset`, for lists paged in the browser. */
export function pageOf<Row>(rows: readonly Row[], offset: number, limit: number): Row[] {
  return rows.slice(offset, offset + limit);
}

/** Offset read from a URL query value: a positive integer, otherwise the first page (0). */
export function parseOffset(value: string | null): number {
  const offset = Number(value ?? "0");
  return Number.isInteger(offset) && offset > 0 ? offset : 0;
}
