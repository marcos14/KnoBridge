import { useSearchParams } from "react-router";

import {
  type AuditFilters,
  type AuditSearch,
  auditSearchParams,
  parseAuditSearch,
} from "@/lib/auditFilters";

/**
 * Filters and page of an audit screen, read from and written to the URL query string, so the
 * filtered view can be shared and survives a reload. A filter change goes back to the first page.
 */
export function useAuditSearch() {
  const [params, setParams] = useSearchParams();
  const search = parseAuditSearch(params);

  function update(next: AuditSearch) {
    setParams(auditSearchParams(next));
  }

  return {
    search,
    setFilters: (filters: AuditFilters) => {
      update({ filters, offset: 0 });
    },
    setOffset: (offset: number) => {
      update({ filters: search.filters, offset });
    },
  };
}
