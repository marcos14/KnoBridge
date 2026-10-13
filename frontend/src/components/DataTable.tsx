import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { pageRange } from "@/lib/pagination";

export interface DataTableColumn<Row> {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  /** Classes of the header and the cells (width, alignment). */
  className?: string;
}

/** Offset pagination of the table; the caller owns the offset (server or browser paging). */
export interface DataTablePagination {
  offset: number;
  limit: number;
  total: number;
  onOffsetChange: (offset: number) => void;
}

interface DataTableProps<Row> {
  /** Accessible name of the table and of its pagination. */
  label: string;
  columns: readonly DataTableColumn<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string;
  /** Shown in place of the rows when there are none (text, or text with the next step's link). */
  emptyMessage: ReactNode;
  pagination?: DataTablePagination;
  /** Marks the table busy while a new page loads (the previous rows stay on screen). */
  busy?: boolean;
}

/**
 * Table of rows with typed columns, an empty state and offset pagination ("1–20 de 45", previous,
 * next). Generic: members, audit, instance administration and conversations reuse it.
 */
export function DataTable<Row>({
  label,
  columns,
  rows,
  rowKey,
  emptyMessage,
  pagination,
  busy = false,
}: DataTableProps<Row>) {
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-md border">
        <Table aria-label={label} aria-busy={busy}>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.key} className={column.className}>
                  {column.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-muted-foreground py-6">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={rowKey(row)}>
                  {columns.map((column) => (
                    <TableCell key={column.key} className={column.className}>
                      {column.cell(row)}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
      {pagination !== undefined && pagination.total > 0 && (
        <TablePagination label={label} {...pagination} />
      )}
    </div>
  );
}

function TablePagination({
  label,
  offset,
  limit,
  total,
  onOffsetChange,
}: DataTablePagination & { label: string }) {
  const { t } = useTranslation();
  const { from, to } = pageRange(offset, limit, total);

  return (
    <nav
      aria-label={t("dataTable.pagination", { label })}
      className="flex flex-wrap items-center justify-between gap-2"
    >
      <p className="text-muted-foreground text-sm">{t("dataTable.range", { from, to, total })}</p>
      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={offset === 0}
          onClick={() => {
            onOffsetChange(Math.max(0, offset - limit));
          }}
        >
          {t("dataTable.previous")}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={to >= total}
          onClick={() => {
            onOffsetChange(offset + limit);
          }}
        >
          {t("dataTable.next")}
        </Button>
      </div>
    </nav>
  );
}
