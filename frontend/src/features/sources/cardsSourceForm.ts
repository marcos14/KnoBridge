import type { CardStatus } from "@/lib/api/tickets";

/**
 * Rules of a `cards` source config (`CardsSourceConfig`, `docs/specs/cards.md`, "Fonte do tipo
 * cards"). The config travels as a plain object in the API, like the other kinds; `anonymize` is
 * the form field shared with the tickets source.
 */
export const CARD_STATUSES = [
  "backlog",
  "in_progress",
  "done",
  "cancelled",
] as const satisfies readonly CardStatus[];

/** Fields of the source form that only a `cards` source uses. */
export interface CardsFormFields {
  includeComments: boolean;
  /** Indexed statuses; at least one. */
  cardStatuses: CardStatus[];
}

/** The defaults of the contract: comments in, every status (anonymized, like tickets). */
export const CARDS_FORM_DEFAULTS: CardsFormFields = {
  includeComments: true,
  cardStatuses: [...CARD_STATUSES],
};

/** The form fields of a stored config; what is missing (other kinds) keeps the defaults. */
export function cardsFieldsFromConfig(config: Record<string, unknown>): CardsFormFields {
  const stored = Array.isArray(config.statuses) ? (config.statuses as unknown[]) : null;
  return {
    includeComments: config.include_comments !== false,
    cardStatuses:
      stored === null
        ? [...CARD_STATUSES]
        : CARD_STATUSES.filter((status) => stored.includes(status)),
  };
}

/** `config` of a cards source, with the statuses in their canonical order. */
export function cardsConfig(
  values: CardsFormFields & { anonymize: boolean },
): Record<string, unknown> {
  return {
    anonymize: values.anonymize,
    include_comments: values.includeComments,
    statuses: CARD_STATUSES.filter((status) => values.cardStatuses.includes(status)),
  };
}
