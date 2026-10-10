import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";

describe("HomePage", () => {
  it("test_home_page_is_shown_at_root_route", () => {
    renderWithProviders({ path: "/" });

    expect(screen.getByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
    expect(screen.getByText("Bem-vindo ao painel do KnoBridge.")).toBeInTheDocument();
  });
});
