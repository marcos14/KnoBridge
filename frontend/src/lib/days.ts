/**
 * Calendar days of the period filters (`YYYY-MM-DD`, from `input[type=date]`) and the instants
 * the API takes for them. A day means the browser's local day; the API receives UTC instants.
 */

const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Parts of a real calendar day written as `YYYY-MM-DD`, or `undefined`. */
function dayParts(value: string): [number, number, number] | undefined {
  const match = DAY.exec(value);
  if (match === null) {
    return undefined;
  }
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(year, month - 1, day);
  if (date.getMonth() !== month - 1 || date.getDate() !== day) {
    return undefined;
  }
  return [year, month, day];
}

/** `value` when it is a real calendar day (`2026-02-30` is not), otherwise `undefined`. */
export function validDay(value: string | null): string | undefined {
  return value !== null && dayParts(value) !== undefined ? value : undefined;
}

/** Start of the local day `day` plus `shift` days, as an ISO 8601 UTC instant. */
export function dayStart(day: string, shift = 0): string | undefined {
  const parts = dayParts(day);
  if (parts === undefined) {
    return undefined;
  }
  const [year, month, date] = parts;
  return new Date(year, month - 1, date + shift).toISOString();
}

/** A period as the API takes it: the half-open interval `[start, end)` of UTC instants. */
export interface InstantPeriod {
  start?: string;
  end?: string;
}

/**
 * The inclusive days `from` and `to` (either may be missing) as `[start of "from", start of the
 * day after "to")`, so the whole last day counts.
 */
export function dayPeriod(from: string | undefined, to: string | undefined): InstantPeriod {
  return {
    start: from === undefined ? undefined : dayStart(from),
    end: to === undefined ? undefined : dayStart(to, 1),
  };
}
