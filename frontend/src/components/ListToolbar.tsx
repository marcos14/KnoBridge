import { type SyntheticEvent, useEffect, useEffectEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { type FilterOption, FilterSelect } from "@/components/FilterSelect";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { normalizeQuery } from "@/lib/listSearch";

/** How long typing must pause before the search goes to the API. */
export const SEARCH_DEBOUNCE_MS = 300;

/** Value of the "all" item of a filter: Radix Select items cannot have an empty value. */
export const ALL_FILTER = "all";

export interface ListToolbarFilter {
  key: string;
  label: string;
  /** Text of the "all" item. */
  allLabel: string;
  /** Chosen value; `undefined` is "all". */
  value: string | undefined;
  options: readonly FilterOption[];
  onChange: (value: string | undefined) => void;
}

export interface ListToolbarSort {
  value: string;
  options: readonly FilterOption[];
  onChange: (value: string) => void;
}

interface ListToolbarProps {
  /** Label of the search box ("Buscar assistentes"). */
  searchLabel: string;
  searchPlaceholder: string;
  /** Search applied now (from the URL). */
  query: string;
  /** Called with the normalized text after a pause in typing, or at once on Enter. */
  onQueryChange: (query: string) => void;
  filters?: readonly ListToolbarFilter[];
  sort: ListToolbarSort;
  /** Shows "Limpar filtros" while a search or a filter narrows the list. */
  onClear?: () => void;
}

/**
 * Search box (debounced), filters and sort of a listing; each filter or sort change applies at
 * once. The caller keeps the state (usually in the URL, via `useListSearch`).
 */
export function ListToolbar({
  searchLabel,
  searchPlaceholder,
  query,
  onQueryChange,
  filters = [],
  sort,
  onClear,
}: ListToolbarProps) {
  const { t } = useTranslation();
  const searchId = useId();
  const sortId = useId();
  const filterId = useId();
  const [text, setText] = useState(query);
  const [appliedQuery, setAppliedQuery] = useState(query);

  // The search changed from outside (Back, a cleared filter, a shared link): show it, unless the
  // box already says the same (a trailing space being typed stays).
  if (query !== appliedQuery) {
    setAppliedQuery(query);
    if (normalizeQuery(text) !== query) {
      setText(query);
    }
  }

  const commit = useEffectEvent((next: string) => {
    onQueryChange(next);
  });

  useEffect(() => {
    const next = normalizeQuery(text);
    if (next === query) {
      return undefined;
    }
    const timer = setTimeout(() => {
      commit(next);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [text, query]);

  function onSubmit(event: SyntheticEvent) {
    event.preventDefault();
    const next = normalizeQuery(text);
    if (next !== query) {
      onQueryChange(next);
    }
  }

  return (
    <div className="flex flex-wrap items-end gap-4">
      <form role="search" onSubmit={onSubmit} className="flex w-full flex-col gap-2 sm:w-72">
        <Label htmlFor={searchId}>{searchLabel}</Label>
        <Input
          id={searchId}
          type="search"
          value={text}
          placeholder={searchPlaceholder}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
      </form>
      {filters.map((filter) => {
        const id = `${filterId}-${filter.key}`;
        return (
          <div key={filter.key} className="flex flex-col gap-2">
            <Label htmlFor={id}>{filter.label}</Label>
            <FilterSelect
              id={id}
              className="w-full sm:w-44"
              value={filter.value ?? ALL_FILTER}
              options={[{ value: ALL_FILTER, label: filter.allLabel }, ...filter.options]}
              onValueChange={(value) => {
                filter.onChange(value === ALL_FILTER ? undefined : value);
              }}
            />
          </div>
        );
      })}
      <div className="flex flex-col gap-2">
        <Label htmlFor={sortId}>{t("listToolbar.sort")}</Label>
        <FilterSelect
          id={sortId}
          className="w-full sm:w-52"
          value={sort.value}
          options={sort.options}
          onValueChange={sort.onChange}
        />
      </div>
      {onClear !== undefined && (
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setText("");
            onClear();
          }}
        >
          {t("listToolbar.clear")}
        </Button>
      )}
    </div>
  );
}
