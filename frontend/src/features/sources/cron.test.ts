import { describe, expect, it } from "vitest";

import { CRON_PRESETS, describeCron, formatCronTime, isCronShape } from "./cron";

describe("isCronShape", () => {
  it.each(["0 3 * * *", "*/15 * * * *", "0 6 * * 1-5", " 0  3 * * MON ", "0 0 1,15 * sun-sat"])(
    "test_is_cron_shape_accepts_%s",
    (cron) => {
      expect(isCronShape(cron)).toBe(true);
    },
  );

  it.each(["", "0 3 * *", "0 3 * * * *", "@daily", "0 3 * * ?", "a b c d e"])(
    "test_is_cron_shape_rejects_%s",
    (cron) => {
      expect(isCronShape(cron)).toBe(false);
    },
  );
});

describe("describeCron", () => {
  it.each([
    ["* * * * *", { kind: "everyMinute" }],
    ["*/15 * * * *", { kind: "everyMinutes", step: 15 }],
    ["5 * * * *", { kind: "hourly", minute: 5 }],
    ["30 */6 * * *", { kind: "everyHours", step: 6, minute: 30 }],
    ["0 3 * * *", { kind: "daily", time: { hour: 3, minute: 0 } }],
    ["0 6 * * 1-5", { kind: "weekdayRange", from: 1, to: 5, time: { hour: 6, minute: 0 } }],
    ["0 2 * * 0", { kind: "weekly", days: [0], time: { hour: 2, minute: 0 } }],
    ["15 8 * * 1,3,7", { kind: "weekly", days: [1, 3, 0], time: { hour: 8, minute: 15 } }],
    ["0 4 10 * *", { kind: "monthly", day: 10, time: { hour: 4, minute: 0 } }],
  ])("test_describe_cron_reads_%s", (cron, expected) => {
    expect(describeCron(cron)).toEqual(expected);
  });

  it.each([
    "0 3 * *",
    "0 3 * 1 *",
    "*/0 * * * *",
    "1-5 * * * *",
    "x */6 * * *",
    "0 */6 * * 1",
    "0 25 * * *",
    "0 3 32 * *",
    "0 3 1 * 1",
    "0 3 * * 5-1",
    "0 3 * * 1-x",
    "0 3 * * MON",
  ])("test_describe_cron_leaves_%s_as_custom", (cron) => {
    expect(describeCron(cron)).toBeUndefined();
  });

  it("test_describe_cron_reads_every_preset", () => {
    for (const preset of CRON_PRESETS) {
      expect(describeCron(preset.cron)).toBeDefined();
    }
  });
});

describe("formatCronTime", () => {
  it("test_format_cron_time_pads_hours_and_minutes", () => {
    expect(formatCronTime({ hour: 3, minute: 5 })).toBe("03:05");
    expect(formatCronTime({ hour: 23, minute: 45 })).toBe("23:45");
  });
});
