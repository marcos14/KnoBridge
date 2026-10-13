import "@/i18n";

import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ListToolbar, type ListToolbarFilter, SEARCH_DEBOUNCE_MS } from "./ListToolbar";

const SORT_OPTIONS = [
  { value: "name", label: "Nome (A–Z)" },
  { value: "-name", label: "Nome (Z–A)" },
];

interface Props {
  query?: string;
  onQueryChange?: (query: string) => void;
  onSortChange?: (value: string) => void;
  filter?: Partial<ListToolbarFilter>;
  onClear?: () => void;
}

function toolbar({
  query = "",
  onQueryChange = vi.fn(),
  onSortChange = vi.fn(),
  filter,
  onClear,
}: Props) {
  return (
    <ListToolbar
      searchLabel="Buscar itens"
      searchPlaceholder="Nome"
      query={query}
      onQueryChange={onQueryChange}
      filters={[
        {
          key: "kind",
          label: "Tipo",
          allLabel: "Todos os tipos",
          value: undefined,
          options: [{ value: "git", label: "Git" }],
          onChange: vi.fn(),
          ...filter,
        },
      ]}
      sort={{ value: "name", options: SORT_OPTIONS, onChange: onSortChange }}
      onClear={onClear}
    />
  );
}

describe("ListToolbar search", () => {
  // Only the debounce timer is faked; typing goes through fireEvent, which needs no timers.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function type(text: string) {
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar itens" }), {
      target: { value: text },
    });
  }

  it("test_list_toolbar_debounces_the_search_until_typing_pauses", () => {
    const onQueryChange = vi.fn();
    render(toolbar({ onQueryChange }));

    type(" no");
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
    });
    type(" nota ");
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS - 1);
    });
    expect(onQueryChange).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onQueryChange).toHaveBeenCalledTimes(1);
    expect(onQueryChange).toHaveBeenCalledWith("nota");
  });

  it("test_list_toolbar_enter_searches_at_once", () => {
    const onQueryChange = vi.fn();
    render(toolbar({ onQueryChange }));

    type("erp");
    fireEvent.submit(screen.getByRole("search"));

    expect(onQueryChange).toHaveBeenCalledWith("erp");
  });

  it("test_list_toolbar_enter_without_change_does_nothing", () => {
    const onQueryChange = vi.fn();
    render(toolbar({ query: "erp", onQueryChange }));

    fireEvent.submit(screen.getByRole("search"));
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });

    expect(onQueryChange).not.toHaveBeenCalled();
  });

  it("test_list_toolbar_follows_a_search_changed_from_outside", () => {
    const { rerender } = render(toolbar({ query: "erp" }));
    expect(screen.getByRole("searchbox", { name: "Buscar itens" })).toHaveValue("erp");

    rerender(toolbar({ query: "" }));

    expect(screen.getByRole("searchbox", { name: "Buscar itens" })).toHaveValue("");
  });

  it("test_list_toolbar_keeps_a_trailing_space_after_the_search_applies", () => {
    const { rerender } = render(toolbar({}));

    type("nota ");
    rerender(toolbar({ query: "nota" }));

    expect(screen.getByRole("searchbox", { name: "Buscar itens" })).toHaveValue("nota ");
  });

  it("test_list_toolbar_clear_empties_the_box_and_calls_back", () => {
    const onClear = vi.fn();
    const onQueryChange = vi.fn();
    render(toolbar({ onClear, onQueryChange }));

    type("abc");
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    act(() => {
      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
    });

    expect(screen.getByRole("searchbox", { name: "Buscar itens" })).toHaveValue("");
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onQueryChange).not.toHaveBeenCalled();
  });
});

describe("ListToolbar filters and sort", () => {
  it("test_list_toolbar_filter_all_item_means_no_filter", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(toolbar({ filter: { value: "git", onChange } }));

    const filter = screen.getByRole("combobox", { name: "Tipo" });
    expect(filter).toHaveTextContent("Git");
    await user.click(filter);
    await user.click(await screen.findByRole("option", { name: "Todos os tipos" }));

    expect(onChange).toHaveBeenCalledWith(undefined);
  });

  it("test_list_toolbar_filter_passes_the_chosen_value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(toolbar({ filter: { onChange } }));

    await user.click(screen.getByRole("combobox", { name: "Tipo" }));
    await user.click(await screen.findByRole("option", { name: "Git" }));

    expect(onChange).toHaveBeenCalledWith("git");
  });

  it("test_list_toolbar_sort_change_applies", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    render(toolbar({ onSortChange }));

    await user.click(screen.getByRole("combobox", { name: "Ordenar por" }));
    await user.click(await screen.findByRole("option", { name: "Nome (Z–A)" }));

    expect(onSortChange).toHaveBeenCalledWith("-name");
  });

  it("test_list_toolbar_hides_clear_without_criteria", () => {
    render(toolbar({}));

    expect(screen.queryByRole("button", { name: "Limpar filtros" })).not.toBeInTheDocument();
  });
});
