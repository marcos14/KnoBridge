import { type SyntheticEvent, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface SearchFormProps {
  placeholder: string;
  /** Called with the typed text when the form is sent (the API searches, not the browser). */
  onSearch: (query: string) => void;
}

/** Search box of the admin listings, sent with Enter or the button (one request per search). */
export function SearchForm({ placeholder, onSearch }: SearchFormProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const [query, setQuery] = useState("");

  function onSubmit(event: SyntheticEvent) {
    event.preventDefault();
    onSearch(query.trim());
  }

  return (
    <form role="search" onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-2 sm:w-80">
        <Label htmlFor={inputId}>{t("admin.search")}</Label>
        <Input
          id={inputId}
          type="search"
          value={query}
          placeholder={placeholder}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </div>
      <Button type="submit" variant="outline">
        {t("admin.searchSubmit")}
      </Button>
    </form>
  );
}
