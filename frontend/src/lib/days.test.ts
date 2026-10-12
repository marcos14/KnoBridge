import { describe, expect, it } from "vitest";

import { dayPeriod, dayStart, validDay } from "./days";

describe("days", () => {
  it("test_valid_day_accepts_only_real_calendar_days", () => {
    expect(validDay("2026-10-01")).toBe("2026-10-01");
    expect(validDay("2026-02-30")).toBeUndefined();
    expect(validDay("2026-13-01")).toBeUndefined();
    expect(validDay("ontem")).toBeUndefined();
    expect(validDay(null)).toBeUndefined();
  });

  it("test_day_start_is_local_midnight_as_utc_instant", () => {
    const start = dayStart("2026-10-01");

    expect(start).toBe(new Date(2026, 9, 1).toISOString());
    expect(start?.endsWith("Z")).toBe(true);
    const local = new Date(start ?? "");
    expect([local.getFullYear(), local.getMonth(), local.getDate(), local.getHours()]).toEqual([
      2026, 9, 1, 0,
    ]);
    expect(dayStart("2026-12-31", 1)).toBe(new Date(2027, 0, 1).toISOString());
    expect(dayStart("2026-02-30")).toBeUndefined();
  });

  it("test_day_period_is_half_open_including_the_last_day", () => {
    expect(dayPeriod("2026-10-01", "2026-10-31")).toEqual({
      start: new Date(2026, 9, 1).toISOString(),
      end: new Date(2026, 10, 1).toISOString(),
    });
    expect(dayPeriod(undefined, undefined)).toEqual({ start: undefined, end: undefined });
  });
});
