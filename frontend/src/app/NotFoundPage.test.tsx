import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";

describe("NotFoundPage", () => {
  it("test_not_found_page_is_shown_for_unknown_route", async () => {
    renderWithProviders({ path: "/does-not-exist" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Página não encontrada" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar para o início" })).toHaveAttribute("href", "/");
  });

  it("test_not_found_page_link_navigates_home", async () => {
    const user = userEvent.setup();
    renderWithProviders({ path: "/does-not-exist/deep" });

    await user.click(await screen.findByRole("link", { name: "Voltar para o início" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Início" })).toBeInTheDocument();
  });
});
