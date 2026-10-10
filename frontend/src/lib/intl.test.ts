import { describe, expect, it } from "vitest";

import { formatDateTime, formatRelativeTime, languageName } from "./intl";

const NOW = new Date("2026-10-10T12:00:00Z");

function secondsFromNow(seconds: number): Date {
  return new Date(NOW.getTime() + seconds * 1000);
}

describe("formatRelativeTime", () => {
  it.each([
    [0, "agora"],
    [-30, "há 30 segundos"],
    [-5 * 60, "há 5 minutos"],
    [2 * 3600, "em 2 horas"],
    [-3 * 86400, "há 3 dias"],
    [-60 * 86400, "há 2 meses"],
    [-2 * 365 * 86400, "há 2 anos"],
  ])("test_format_relative_time_%s_seconds_is_%s", (seconds, expected) => {
    expect(formatRelativeTime(secondsFromNow(seconds), NOW, "pt-BR")).toBe(expected);
  });

  it("test_format_relative_time_rounds_to_largest_whole_unit", () => {
    expect(formatRelativeTime(secondsFromNow(125), NOW, "pt-BR")).toBe("em 2 minutos");
  });
});

describe("formatDateTime", () => {
  it("test_format_date_time_uses_locale_and_time_zone", () => {
    expect(formatDateTime(new Date("2026-10-01T09:00:00Z"), "pt-BR", "UTC")).toBe(
      "1 de out. de 2026, 09:00",
    );
  });
});

describe("languageName", () => {
  it("test_language_name_in_interface_language", () => {
    expect(languageName("pt-BR", "pt-BR")).toBe("português (Brasil)");
    expect(languageName("en", "pt-BR")).toBe("inglês");
  });

  it("test_language_name_unknown_tag_is_the_tag", () => {
    expect(languageName("zz", "pt-BR")).toBe("zz");
  });
});
