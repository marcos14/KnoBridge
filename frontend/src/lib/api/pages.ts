/** Largest page the workspace listings of the API accept (`limit` up to 200). */
export const MAX_PAGE_SIZE = 200;

interface Page<Item> {
  items: Item[];
  total: number;
}

/**
 * Every item of an offset-paged listing, reading pages of `MAX_PAGE_SIZE` until `total` (or an
 * empty page, should the list shrink while it is read). For short lists the screen pages itself.
 */
export async function fetchAllPages<Item>(
  fetchPage: (query: { limit: number; offset: number }) => Promise<Page<Item>>,
): Promise<Item[]> {
  const items: Item[] = [];
  for (;;) {
    const page = await fetchPage({ limit: MAX_PAGE_SIZE, offset: items.length });
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) {
      return items;
    }
  }
}
