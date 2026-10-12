import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import type { TicketUploadError, TicketUploadReport } from "@/lib/api/tickets";
import { pageOf } from "@/lib/pagination";

import { formatCount } from "../format";
import { duplicateOf, ticketProblems, uploadErrorPosition } from "./ticketFormat";

/** Rejected items per page of the report (up to 1000 come back). */
export const UPLOAD_ERRORS_PAGE_SIZE = 20;

const COUNTS = ["queued", "unchanged", "stale", "rejected"] as const;

/** Item error codes the panel names; anything else shows the server's message. */
const KNOWN_CODES = [
  "validation_error",
  "ticket_too_large",
  "duplicate_in_batch",
  "invalid_json",
] as const;

type KnownCode = (typeof KNOWN_CODES)[number];

function knownCode(code: string): KnownCode | undefined {
  return KNOWN_CODES.find((item) => item === code);
}

/** The outcome of an upload: totals, the sync it asked for and the rejected items. */
export function UploadReport({ report }: { report: TicketUploadReport }) {
  const { t, i18n } = useTranslation();
  const [offset, setOffset] = useState(0);
  const byLine = report.format === "jsonl";

  const columns: DataTableColumn<TicketUploadError>[] = [
    {
      key: "position",
      header: byLine ? t("tickets.upload.columns.line") : t("tickets.upload.columns.index"),
      cell: (row) => uploadErrorPosition(row)?.value ?? "—",
    },
    {
      key: "ticket",
      header: t("tickets.upload.columns.ticket"),
      cell: (row) => row.external_id ?? "—",
    },
    {
      key: "error",
      header: t("tickets.upload.columns.error"),
      cell: (row) => <ErrorDetail error={row} byLine={byLine} />,
    },
  ];

  return (
    <section aria-labelledby="ticket-upload-report" className="flex flex-col gap-3">
      <h2 id="ticket-upload-report" className="text-lg font-semibold">
        {t("tickets.upload.report.title")}
      </h2>
      <p role="status" className="text-sm">
        {t("tickets.upload.report.summary", {
          total: formatCount(report.total, i18n.language),
          format: report.format.toUpperCase(),
        })}{" "}
        {t(`tickets.upload.report.sync.${report.sync}`)}
      </p>
      <dl className="grid w-fit grid-cols-[auto_auto] gap-x-4 gap-y-1 text-sm">
        {COUNTS.map((key) => (
          <div key={key} className="contents">
            <dt className="text-muted-foreground">{t(`tickets.upload.report.counts.${key}`)}</dt>
            <dd>{formatCount(report.counts[key], i18n.language)}</dd>
          </div>
        ))}
      </dl>
      {report.errors.length > 0 && (
        <>
          <h3 className="text-sm font-semibold">{t("tickets.upload.report.errorsTitle")}</h3>
          {report.errors_truncated && (
            <p className="text-sm">
              {t("tickets.upload.report.truncated", {
                shown: formatCount(report.errors.length, i18n.language),
              })}
            </p>
          )}
          <DataTable
            label={t("tickets.upload.report.errorsLabel")}
            columns={columns}
            rows={pageOf(report.errors, offset, UPLOAD_ERRORS_PAGE_SIZE)}
            rowKey={(row) => `${String(row.line)}-${String(row.index)}`}
            emptyMessage=""
            pagination={{
              offset,
              limit: UPLOAD_ERRORS_PAGE_SIZE,
              total: report.errors.length,
              onOffsetChange: setOffset,
            }}
          />
        </>
      )}
    </section>
  );
}

function ErrorDetail({ error, byLine }: { error: TicketUploadError; byLine: boolean }) {
  const { t } = useTranslation();
  const code = knownCode(error.code);
  const problems = ticketProblems(error.details);
  const first = code === "duplicate_in_batch" ? duplicateOf(error.details) : null;
  return (
    <div className="flex flex-col gap-1">
      <span>{code === undefined ? error.message : t(`tickets.upload.codes.${code}`)}</span>
      {first !== null && (
        <span className="text-muted-foreground text-xs">
          {byLine
            ? t("tickets.upload.duplicateOfLine", { first })
            : t("tickets.upload.duplicateOfIndex", { first })}
        </span>
      )}
      {problems.length > 0 && (
        <ul className="text-muted-foreground font-mono text-xs">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
