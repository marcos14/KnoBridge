import { useTranslation } from "react-i18next";

import type { Source } from "@/lib/api/sources";

import { ticketsFieldsFromConfig } from "../ticketsSourceForm";

/** Header lines of a tickets source: where tickets come from and how they are indexed. */
export function TicketsSummary({ source }: { source: Source }) {
  const { t } = useTranslation();
  const { anonymize, includeInternalNotes, statuses } = ticketsFieldsFromConfig(source.config);
  return (
    <>
      <p className="text-sm">{t("tickets.summary.origin")}</p>
      <p className="text-sm">
        {t(anonymize ? "tickets.summary.anonymized" : "tickets.summary.notAnonymized")}{" "}
        {t(
          includeInternalNotes
            ? "tickets.summary.withInternalNotes"
            : "tickets.summary.withoutInternalNotes",
        )}
      </p>
      <p className="text-sm">
        {t("tickets.summary.statuses", {
          statuses: statuses.map((status) => t(`tickets.status.${status}`)).join(", "),
        })}
      </p>
    </>
  );
}
