import { useSearchParams } from "react-router";

import {
  type ListSearch,
  type ListSearchSpec,
  listSearchParams,
  parseListSearch,
} from "@/lib/listSearch";

/**
 * Search, filters, sort and page of a listing, read from and written to the URL query string. A
 * new search, filter or sort goes back to page one. Each change starts from the URL as it is at
 * that moment, so a debounced search does not undo a page change made in between.
 */
export function useListSearch<Filter extends string, Sort extends string>(
  spec: ListSearchSpec<Filter, Sort>,
) {
  const [params, setParams] = useSearchParams();
  const search = parseListSearch(params, spec);

  function update(
    change: (current: ListSearch<Filter, Sort>) => ListSearch<Filter, Sort>,
    replace = false,
  ) {
    setParams((current) => listSearchParams(change(parseListSearch(current, spec)), spec), {
      replace,
    });
  }

  return {
    search,
    // Typing replaces the history entry: Back leaves the screen instead of undoing letters.
    setQuery: (query: string) => {
      update((current) => ({ ...current, query, offset: 0 }), true);
    },
    setFilter: (key: Filter, value: string | undefined) => {
      update((current) => ({
        ...current,
        filters: { ...current.filters, [key]: value },
        offset: 0,
      }));
    },
    /** Takes the value of the sort select; one the listing does not offer is ignored. */
    setSort: (value: string) => {
      const sort = spec.sorts.find((item) => item === value);
      if (sort !== undefined) {
        update((current) => ({ ...current, sort, offset: 0 }));
      }
    },
    setOffset: (offset: number) => {
      update((current) => ({ ...current, offset }));
    },
    clear: () => {
      update((current) => ({ ...current, query: "", filters: {}, offset: 0 }));
    },
  };
}
