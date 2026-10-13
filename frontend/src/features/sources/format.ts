import type { TFunction } from "i18next";

import { translateApiErrorCode } from "@/i18n/apiErrors";
import type { Run, Source } from "@/lib/api/sources";

import { type CronDescription, describeCron, formatCronTime } from "./cron";

// Shared with other areas (usage and costs) from `lib/`; re-exported for the sources screens.
export { formatCount, formatUsd } from "@/lib/numberFormat";

/** Milliseconds as "45 s", "1 min 59 s" or "2 h 5 min" (seconds are dropped past one hour). */
export function formatDuration(milliseconds: number): string {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  const h = String(hours);
  const min = String(minutes);
  const s = String(rest);
  if (hours > 0) {
    return minutes > 0 ? `${h} h ${min} min` : `${h} h`;
  }
  if (minutes > 0) {
    return rest > 0 ? `${min} min ${s} s` : `${min} min`;
  }
  return `${s} s`;
}

/**
 * How long the run took, or has been running until `now`; `undefined` before it starts (queued)
 * or when it ended without starting (cancelled while queued).
 */
export function runDuration(run: Run, now: Date): string | undefined {
  if (run.started_at === null) {
    return undefined;
  }
  const end = run.finished_at === null ? now : new Date(run.finished_at);
  return formatDuration(end.getTime() - new Date(run.started_at).getTime());
}

/** Names of the days of week in the interface language, 0 (Sunday) to 6. */
function dayName(day: number, t: TFunction): string {
  return t(`sources.cron.days.${String(day) as "0"}`);
}

function describe(description: CronDescription, t: TFunction, locale: string): string {
  switch (description.kind) {
    case "everyMinute":
      return t("sources.cron.everyMinute");
    case "everyMinutes":
      return t("sources.cron.everyMinutes", { count: description.step });
    case "hourly":
      return t("sources.cron.hourly", { minute: description.minute });
    case "everyHours":
      return t("sources.cron.everyHours", {
        count: description.step,
        minute: description.minute,
      });
    case "daily":
      return t("sources.cron.daily", { time: formatCronTime(description.time) });
    case "weekdayRange":
      return t("sources.cron.weekdayRange", {
        from: dayName(description.from, t),
        to: dayName(description.to, t),
        time: formatCronTime(description.time),
      });
    case "weekly":
      return t("sources.cron.weekly", {
        days: new Intl.ListFormat(locale, { type: "conjunction" }).format(
          description.days.map((day) => dayName(day, t)),
        ),
        time: formatCronTime(description.time),
      });
    case "monthly":
      return t("sources.cron.monthly", {
        day: description.day,
        time: formatCronTime(description.time),
      });
  }
}

/** The schedule in words ("Todos os dias às 03:00 (UTC)"), or "custom" for an unknown format. */
export function cronText(cron: string, t: TFunction, locale: string): string {
  const description = describeCron(cron);
  return description === undefined ? t("sources.cron.custom") : describe(description, t, locale);
}

/**
 * Why a runner or tickets source is unreachable (`details.reason` of `source_unavailable`): the
 * runner's state, or a tickets source without a send token.
 */
const TEST_REASONS = [
  "runner_offline",
  "runner_revoked",
  "repository_not_served",
  "ingest_token_missing",
] as const;

type TestReason = (typeof TEST_REASONS)[number];

function testReason(details: unknown): TestReason | undefined {
  const reason =
    typeof details === "object" && details !== null && "reason" in details
      ? details.reason
      : undefined;
  return TEST_REASONS.find((item) => item === reason);
}

/**
 * Reason shown when "Testar conexão" fails: the source's own reason when `source_unavailable`
 * carries one, otherwise the message of the error code.
 */
export function testFailureReason(
  error: { code: string; details?: unknown },
  t: TFunction,
): string {
  const reason = error.code === "source_unavailable" ? testReason(error.details) : undefined;
  return reason === undefined
    ? translateApiErrorCode(error.code, t)
    : t(`sources.testReasons.${reason}`);
}

/** The minimum level of a source by name, saying when it is the default of its kind. */
export function minLevelText(
  source: Pick<Source, "min_level" | "min_level_is_default">,
  t: TFunction,
): string {
  const level = t(`workspaceSettings.levels.names.${source.min_level}`);
  return source.min_level_is_default ? t("sources.detail.minLevelDefault", { level }) : level;
}
