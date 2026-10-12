/**
 * Five-field cron expressions (UTC) of a source's schedule: a shape check for the form and a
 * reading of the common formats. The backend (`croniter`) is the judge of what is valid; anything
 * this module cannot read is "custom", never an error.
 */

/** Same limit as the backend (`CRON_MAX_LENGTH`). */
export const CRON_MAX_LENGTH = 100;

/** Ready-made schedules offered by the form, in order. */
export const CRON_PRESETS = [
  { key: "hourly", cron: "0 * * * *" },
  { key: "every6Hours", cron: "0 */6 * * *" },
  { key: "daily3", cron: "0 3 * * *" },
  { key: "weekdays6", cron: "0 6 * * 1-5" },
  { key: "sunday2", cron: "0 2 * * 0" },
] as const;

export type CronPresetKey = (typeof CRON_PRESETS)[number]["key"];

/** The expression split on blanks (the backend normalizes the same way). */
function fieldsOf(cron: string): string[] {
  return cron.trim().split(/\s+/);
}

const FIELD_PATTERN = /^[\d*,/-]+$|^[A-Za-z]{3}(-[A-Za-z]{3})?$/;

/**
 * Whether `cron` looks like a five-field expression of numbers, `*`, `,`, `-`, `/` or three-letter
 * names. The server still validates ranges and the rest.
 */
export function isCronShape(cron: string): boolean {
  const fields = fieldsOf(cron);
  return fields.length === 5 && fields.every((field) => FIELD_PATTERN.test(field));
}

/** A time of day, from the minute and hour fields. */
export interface CronTime {
  hour: number;
  minute: number;
}

/** The reading of an expression in one of the common formats. Days of week: 0 is Sunday. */
export type CronDescription =
  | { kind: "everyMinute" }
  | { kind: "everyMinutes"; step: number }
  | { kind: "hourly"; minute: number }
  | { kind: "everyHours"; step: number; minute: number }
  | { kind: "daily"; time: CronTime }
  | { kind: "weekdayRange"; from: number; to: number; time: CronTime }
  | { kind: "weekly"; days: number[]; time: CronTime }
  | { kind: "monthly"; day: number; time: CronTime };

/** `field` as a whole number in `[min, max]`, or `undefined`. */
function numberIn(field: string, min: number, max: number): number | undefined {
  if (!/^\d+$/.test(field)) {
    return undefined;
  }
  const value = Number(field);
  return value >= min && value <= max ? value : undefined;
}

/** The `N` of `*\/N`, at least 1. */
function stepOf(field: string, max: number): number | undefined {
  return field.startsWith("*/") ? numberIn(field.slice(2), 1, max) : undefined;
}

/** Day of week 0–6 (7 is Sunday too). */
function weekday(field: string): number | undefined {
  const value = numberIn(field, 0, 7);
  return value === undefined ? undefined : value % 7;
}

function weekdaysOf(field: string, time: CronTime): CronDescription | undefined {
  const bounds = field.split("-");
  if (bounds.length === 2) {
    const [from, to] = bounds.map(weekday);
    return from === undefined || to === undefined || from >= to
      ? undefined
      : { kind: "weekdayRange", from, to, time };
  }
  const days = field.split(",").map(weekday);
  return days.every((day) => day !== undefined) ? { kind: "weekly", days, time } : undefined;
}

function daysOf(
  time: CronTime,
  dayOfMonth: string,
  dayOfWeek: string,
): CronDescription | undefined {
  if (dayOfMonth === "*" && dayOfWeek === "*") {
    return { kind: "daily", time };
  }
  if (dayOfWeek === "*") {
    const day = numberIn(dayOfMonth, 1, 31);
    return day === undefined ? undefined : { kind: "monthly", day, time };
  }
  return dayOfMonth === "*" ? weekdaysOf(dayOfWeek, time) : undefined;
}

/** Minute, hour, day of month and day of week of an expression whose month is `*`. */
function describeFields(
  minute: string,
  hour: string,
  dayOfMonth: string,
  dayOfWeek: string,
): CronDescription | undefined {
  const everyDay = dayOfMonth === "*" && dayOfWeek === "*";
  const atMinute = numberIn(minute, 0, 59);
  if (everyDay && hour === "*") {
    if (minute === "*") {
      return { kind: "everyMinute" };
    }
    const step = stepOf(minute, 59);
    if (step !== undefined) {
      return { kind: "everyMinutes", step };
    }
    return atMinute === undefined ? undefined : { kind: "hourly", minute: atMinute };
  }
  if (atMinute === undefined) {
    return undefined;
  }
  const hours = stepOf(hour, 23);
  if (hours !== undefined) {
    return everyDay ? { kind: "everyHours", step: hours, minute: atMinute } : undefined;
  }
  const atHour = numberIn(hour, 0, 23);
  return atHour === undefined
    ? undefined
    : daysOf({ hour: atHour, minute: atMinute }, dayOfMonth, dayOfWeek);
}

/** The common format `cron` is in, or `undefined` for anything else (shown as custom). */
export function describeCron(cron: string): CronDescription | undefined {
  const fields = fieldsOf(cron);
  if (fields.length !== 5 || fields[3] !== "*") {
    return undefined;
  }
  const [minute, hour, dayOfMonth, , dayOfWeek] = fields as [
    string,
    string,
    string,
    string,
    string,
  ];
  return describeFields(minute, hour, dayOfMonth, dayOfWeek);
}

/** `HH:MM`. */
export function formatCronTime({ hour, minute }: CronTime): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}
