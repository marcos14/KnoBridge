import type { TicketStatus } from "@/lib/citationLocation";

/**
 * Rules of a `tickets` source config (`TicketsSourceConfig`, `docs/specs/chamados.md`, "Fonte do
 * tipo tickets"). The config travels as a plain object in the API, like the other kinds.
 */
export const TICKET_STATUSES = [
  "open",
  "pending",
  "resolved",
  "closed",
] as const satisfies readonly TicketStatus[];

/** Fields of the source form that only a `tickets` source uses. */
export interface TicketsFormFields {
  includeInternalNotes: boolean;
  anonymize: boolean;
  /** Indexed statuses; at least one. */
  statuses: TicketStatus[];
}

/** The defaults of the contract: no internal notes, anonymized, every status. */
export const TICKETS_FORM_DEFAULTS: TicketsFormFields = {
  includeInternalNotes: false,
  anonymize: true,
  statuses: [...TICKET_STATUSES],
};

/** The form fields of a stored config; what is missing (other kinds) keeps the defaults. */
export function ticketsFieldsFromConfig(config: Record<string, unknown>): TicketsFormFields {
  const stored = Array.isArray(config.statuses) ? (config.statuses as unknown[]) : null;
  return {
    includeInternalNotes: config.include_internal_notes === true,
    anonymize: config.anonymize !== false,
    statuses:
      stored === null
        ? [...TICKET_STATUSES]
        : TICKET_STATUSES.filter((status) => stored.includes(status)),
  };
}

/** `config` of a tickets source, with the statuses in their canonical order. */
export function ticketsConfig(values: TicketsFormFields): Record<string, unknown> {
  return {
    include_internal_notes: values.includeInternalNotes,
    anonymize: values.anonymize,
    statuses: TICKET_STATUSES.filter((status) => values.statuses.includes(status)),
  };
}
