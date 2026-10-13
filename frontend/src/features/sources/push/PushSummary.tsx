import { useTranslation } from "react-i18next";

import type { Source } from "@/lib/api/sources";

import { cardsFieldsFromConfig } from "../cardsSourceForm";
import { ticketsFieldsFromConfig } from "../ticketsSourceForm";

/** Header lines of a tickets or cards source: where items come from and how they are indexed. */
export function PushSummary({ source }: { source: Source }) {
  const { t } = useTranslation();
  const { anonymize, includeInternalNotes, statuses } = ticketsFieldsFromConfig(source.config);
  const anonymized = t(anonymize ? "tickets.summary.anonymized" : "tickets.summary.notAnonymized");

  if (source.kind === "cards") {
    const { includeComments, cardStatuses } = cardsFieldsFromConfig(source.config);
    return (
      <>
        <p className="text-sm">{t("cards.summary.origin")}</p>
        <p className="text-sm">
          {anonymized}{" "}
          {t(includeComments ? "cards.summary.withComments" : "cards.summary.withoutComments")}
        </p>
        <p className="text-sm">
          {t("cards.summary.statuses", {
            statuses: cardStatuses.map((status) => t(`cards.status.${status}`)).join(", "),
          })}
        </p>
      </>
    );
  }
  return (
    <>
      <p className="text-sm">{t("tickets.summary.origin")}</p>
      <p className="text-sm">
        {anonymized}{" "}
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
