import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "@/i18n";

import { LevelBadge } from "./LevelBadge";

describe("LevelBadge", () => {
  it.each([
    ["end_user", "Nível: Usuário final"],
    ["support", "Nível: Suporte"],
    ["product_dev", "Nível: Desenvolvimento e produto"],
  ] as const)("test_level_badge_of_%s_names_the_level", (level, text) => {
    render(<LevelBadge level={level} />);

    expect(screen.getByText(text)).toBeVisible();
  });
});
