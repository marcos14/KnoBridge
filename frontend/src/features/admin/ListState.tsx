import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

interface ListStateProps<Data> {
  query: UseQueryResult<Data>;
  /** Text shown while the first page loads. */
  loading: string;
  /** Text of the load error (default: the list one). */
  failed?: string;
  children: (data: Data) => ReactNode;
}

/** Loading text, load error with "try again", or the list itself once the data is there. */
export function ListState<Data>({ query, loading, failed, children }: ListStateProps<Data>) {
  const { t } = useTranslation();

  if (query.isPending) {
    return (
      <p role="status" className="text-sm">
        {loading}
      </p>
    );
  }
  if (query.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert" className="text-sm">
          {failed ?? t("admin.loadFailed")}
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void query.refetch();
          }}
        >
          {t("admin.retry")}
        </Button>
      </div>
    );
  }
  return children(query.data);
}
