import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";

describe("Layout", () => {
  it("test_layout_renders_translated_title", () => {
    renderWithProviders();

    expect(screen.getByRole("banner")).toHaveTextContent("KnoBridge");
  });

  it("test_layout_renders_landmarks", () => {
    renderWithProviders();

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("test_layout_renders_child_route_inside_main", () => {
    renderWithProviders();

    expect(screen.getByRole("main")).toContainElement(
      screen.getByRole("heading", { level: 1, name: "Início" }),
    );
  });
});
