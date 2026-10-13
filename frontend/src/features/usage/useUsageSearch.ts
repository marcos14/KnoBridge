import { useSearchParams } from "react-router";

import { parseUsageSearch, type UsageSearch, usageSearchParams } from "@/lib/usagePeriod";

/**
 * Period and grouping of the usage screen, read from and written to the URL query string, so the
 * view can be shared and survives a reload.
 */
export function useUsageSearch() {
  const [params, setParams] = useSearchParams();
  const search = parseUsageSearch(params);

  return {
    search,
    setSearch: (next: UsageSearch) => {
      setParams(usageSearchParams(next));
    },
  };
}
