/** Date and language formatting with `Intl`, in the interface language. */

const SECOND = 1;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const MONTH = 30 * DAY;
const YEAR = 365 * DAY;

/** Largest unit first: the first one the distance reaches is used. */
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", YEAR],
  ["month", MONTH],
  ["day", DAY],
  ["hour", HOUR],
  ["minute", MINUTE],
];

/**
 * Distance from `now` to `date` in words ("há 5 minutos", "em 2 horas", "agora"), in the largest
 * whole unit it reaches.
 */
export function formatRelativeTime(date: Date, now: Date, locale: string): string {
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const format = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) {
      return format.format(Math.round(seconds / size), unit);
    }
  }
  return format.format(seconds, "second");
}

/**
 * Date and time for reading ("10 de out. de 2026, 14:30"). `timeZone` defaults to the browser's;
 * tests pin it.
 */
export function formatDateTime(date: Date, locale: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(date);
}

/** Name of a language in the interface language ("português (Brasil)"), or the tag itself. */
export function languageName(tag: string, locale: string): string {
  return new Intl.DisplayNames([locale], { type: "language", fallback: "none" }).of(tag) ?? tag;
}
