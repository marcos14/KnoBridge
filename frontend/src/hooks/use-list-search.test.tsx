import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it } from "vitest";

import { type ListSearchSpec, oneOf } from "@/lib/listSearch";

import { useListSearch } from "./use-list-search";

const SPEC: ListSearchSpec<"kind", "name" | "-name"> = {
  filters: { kind: oneOf(["git", "folder"]) },
  sorts: ["name", "-name"],
};

/** Renders the hook inside a memory router started at `/list?<search>`. */
function renderListSearch(search: string) {
  let router: ReturnType<typeof createMemoryRouter> | undefined;
  const wrapper = ({ children }: { children: ReactNode }) => {
    router ??= createMemoryRouter([{ path: "/list", element: children }], {
      initialEntries: [`/list?${search}`],
    });
    return <RouterProvider router={router} />;
  };
  const result = renderHook(() => useListSearch(SPEC), { wrapper });
  const location = () => router?.state.location;
  const historyAction = () => router?.state.historyAction;
  return { ...result, location, historyAction };
}

describe("useListSearch", () => {
  it("test_use_list_search_filter_change_goes_back_to_page_one", () => {
    const { result, location, historyAction } = renderListSearch("q=erp&offset=40");

    act(() => {
      result.current.setFilter("kind", "git");
    });

    expect(location()?.search).toBe("?q=erp&kind=git");
    expect(historyAction()).toBe("PUSH");
    expect(result.current.search.filters).toEqual({ kind: "git" });
  });

  it("test_use_list_search_ignores_a_sort_the_listing_does_not_offer", () => {
    const { result, location } = renderListSearch("offset=20");

    act(() => {
      result.current.setSort("size");
    });
    expect(location()?.search).toBe("?offset=20");

    act(() => {
      result.current.setSort("-name");
    });
    expect(location()?.search).toBe("?sort=-name");
  });

  it("test_use_list_search_query_replaces_the_history_entry", () => {
    const { result, location, historyAction } = renderListSearch("offset=20");

    act(() => {
      result.current.setQuery("nota");
    });

    expect(location()?.search).toBe("?q=nota");
    expect(historyAction()).toBe("REPLACE");
  });

  it("test_use_list_search_page_and_clear_keep_the_sort", () => {
    const { result, location } = renderListSearch("q=erp&kind=folder&sort=-name");

    act(() => {
      result.current.setOffset(20);
    });
    expect(location()?.search).toBe("?q=erp&kind=folder&sort=-name&offset=20");

    act(() => {
      result.current.clear();
    });
    expect(location()?.search).toBe("?sort=-name");
  });
});
