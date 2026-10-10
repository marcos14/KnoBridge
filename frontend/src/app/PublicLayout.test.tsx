import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { meUnauthenticated } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

describe("PublicLayout", () => {
  it("test_public_layout_renders_landmarks_and_title", async () => {
    server.use(meUnauthenticated);
    renderWithProviders({ path: "/login" });

    const heading = await screen.findByRole("heading", { level: 1, name: "Entrar" });
    expect(screen.getByRole("banner")).toHaveTextContent("KnoBridge");
    expect(screen.getByRole("main")).toContainElement(heading);
  });

  it("test_public_layout_renders_api_status_in_header", async () => {
    renderWithProviders({ path: "/login" });

    expect(await screen.findByText("API: disponível")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toContainElement(screen.getByRole("status"));
  });

  it("test_public_layout_has_no_side_menu", async () => {
    renderWithProviders({ path: "/forgot-password" });

    await screen.findByRole("heading", { level: 1, name: "Recuperar senha" });
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
