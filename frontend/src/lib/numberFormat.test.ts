import { describe, expect, it } from "vitest";

import { formatCount, formatUsd } from "./numberFormat";

// Intl separates currency and amount with a no-break space.
const usd = (text: string) => text.replace(/\s/g, " ");

describe("formatUsd", () => {
  it("test_format_usd_keeps_small_costs_readable", () => {
    expect(usd(formatUsd(0.000048, "pt-BR"))).toBe("US$ 0,000048");
    expect(usd(formatUsd(0.001, "pt-BR"))).toBe("US$ 0,0010");
  });

  it("test_format_usd_uses_cents_from_one_cent_up", () => {
    expect(usd(formatUsd(1.5, "pt-BR"))).toBe("US$ 1,50");
    expect(usd(formatUsd(0, "pt-BR"))).toBe("US$ 0,00");
  });

  it("test_format_usd_shows_dash_for_unknown_cost", () => {
    expect(formatUsd(null, "pt-BR")).toBe("—");
  });
});

describe("formatCount", () => {
  it("test_format_count_groups_thousands", () => {
    expect(formatCount(51000, "pt-BR")).toBe("51.000");
  });
});
