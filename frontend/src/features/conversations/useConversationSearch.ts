import { useSearchParams } from "react-router";

import {
  type ConversationFilters,
  type ConversationSearch,
  conversationSearchParams,
  parseConversationSearch,
} from "@/lib/conversationFilters";

/**
 * Filters and page of the conversations screen, read from and written to the URL query string, so
 * the filtered view can be shared and survives a reload. A filter change goes back to page one.
 */
export function useConversationSearch() {
  const [params, setParams] = useSearchParams();
  const search = parseConversationSearch(params);

  function update(next: ConversationSearch) {
    setParams(conversationSearchParams(next));
  }

  return {
    search,
    setFilters: (filters: ConversationFilters) => {
      update({ filters, offset: 0 });
    },
    setOffset: (offset: number) => {
      update({ filters: search.filters, offset });
    },
  };
}
