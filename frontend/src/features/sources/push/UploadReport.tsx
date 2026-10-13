import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DataTable, type DataTableColumn } from "@/components/DataTable";
import type { PushSourceKind, TicketUploadError, TicketUploadReport } from "@/lib/api/tickets";
import { pageOf } from "@/lib/pagination";

import { formatCount } from "../format";
import { duplicateOf, itemProblems, knownUploadCode, uploadErrorPosition } from "./pushFormat";

/** Rejected items per page of the report (up to 1000 come back). */
export const UPLOAD_ERRORS_PAGE_SIZE = 20;

const COUNTS = ["queued", "unchanged", "stale", "rejected"] as const;

interface UploadReportProps {
  /** Tickets or cards: names the items and their error codes. */
  kind: PushSourceKind;
  report: TicketUploadReport;
}

/** The outcome of an upload: totals, the sync it asked for and the rejected items. */
export function UploadReport({ kind, report }: UploadReportProps) {
  const { t, i18n } = useTranslation();
  const [offset, setOffset] = useState(0);
  const byLine = report.format === "jsonl";
  const sync =
    report.sync === "pending" || report.sync === "deferred"
      ? t(`${kind}.upload.sync.${report.sync}`)
      : t(`ingest.upload.report.sync.${report.sync}`);

  const columns: DataTableColumn<TicketUploadError>[] = [
    {
      key: "position",
      header: byLine ? t("ingest.upload.columns.line") : t("ingest.upload.columns.index"),
      cell: (row) => uploadErrorPosition(row)?.value ?? "—",
    },
    {
      key: "item",
      header: t(`${kind}.upload.item`),
      cell: (row) => row.external_id ?? "—",
    },
    {
      key: "error",
      header: t("ingest.upload.columns.error"),
      cell: (row) => <ErrorDetail kind={kind} error={row} byLine={byLine} />,
    },
  ];

  return (
    <section aria-labelledby="ingest-upload-report" className="flex flex-col gap-3">
      <h2 id="ingest-upload-report" className="text-lg font-semibold">
        {t("ingest.upload.report.title")}
      </h2>
      <p role="status" className="text-sm">
        {t("ingest.upload.report.summary", {
          total: formatCount(report.total, i18n.language),
          format: report.format.toUpperCase(),
        })}{" "}
        {sync}
      </p>
      <dl className="grid w-fit grid-cols-[auto_auto] gap-x-4 gap-y-1 text-sm">
        {COUNTS.map((key) => (
          <div key={key} className="contents">
            <dt className="text-muted-foreground">{t(`ingest.upload.report.counts.${key}`)}</dt>
            <dd>{formatCount(report.counts[key], i18n.language)}</dd>
          </div>
        ))}
      </dl>
      {report.errors.length > 0 && (
        <>
          <h3 className="text-sm font-semibold">{t("ingest.upload.report.errorsTitle")}</h3>
          {report.errors_truncated && (
            <p className="text-sm">
              {t("ingest.upload.report.truncated", {
                shown: formatCount(report.errors.length, i18n.language),
              })}
            </p>
          )}
          <DataTable
            label={t("ingest.upload.report.errorsLabel")}
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

interface ErrorDetailProps {
  kind: PushSourceKind;
  error: TicketUploadError;
  byLine: boolean;
}

function ErrorDetail({ kind, error, byLine }: ErrorDetailProps) {
  const { t } = useTranslation();
  const code = kind === "cards" ? knownCardCode(error.code) : knownTicketCode(error.code);
  const problems = itemProblems(error.details);
  const first = error.code === "duplicate_in_batch" ? duplicateOf(error.details) : null;
  return (
    <div className="flex flex-col gap-1">
      <span>{code === undefined ? error.message : t(code)}</span>
      {first !== null && (
        <span className="text-muted-foreground text-xs">
          {byLine
            ? t("ingest.upload.duplicateOfLine", { first })
            : t("ingest.upload.duplicateOfIndex", { first })}
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

/** The i18n key of a known code, per kind (the two lists differ in the size limit's code). */
function knownTicketCode(code: string) {
  const known = knownUploadCode("tickets", code);
  return known === undefined ? undefined : (`tickets.upload.codes.${known}` as const);
}

function knownCardCode(code: string) {
  const known = knownUploadCode("cards", code);
  return known === undefined ? undefined : (`cards.upload.codes.${known}` as const);
}
