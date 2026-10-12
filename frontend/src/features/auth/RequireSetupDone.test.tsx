import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { setupStatusDone, setupStatusNeeded, setupStatusServerError } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

describe("RequireSetupDone", () => {
  it("test_require_setup_done_redirects_to_setup_on_fresh_instance", async () => {
    server.use(setupStatusNeeded);
    const { router } = renderWithProviders({ path: "/login" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Configuração inicial" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/setup");
  });

  it("test_require_setup_done_redirects_authenticated_routes_to_setup", async () => {
    server.use(setupStatusNeeded);
    const { router } = renderWithProviders({ path: "/w/any/settings" });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/setup");
    });
  });

  it("test_require_setup_done_lets_public_route_through_after_setup", async () => {
    renderWithProviders({ path: "/forgot-password" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Recuperar senha" }),
    ).toBeInTheDocument();
  });

  it("test_require_setup_done_shows_loading_while_status_is_pending", () => {
    server.use(
      http.get("*/v1/setup/status", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    renderWithProviders({ path: "/login" });

    expect(screen.getByText("Carregando…")).toBeInTheDocument();
  });

  it("test_require_setup_done_offers_retry_when_status_fails", async () => {
    const user = userEvent.setup();
    server.use(setupStatusServerError);
    renderWithProviders({ path: "/login" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a página.",
    );
    server.use(setupStatusDone);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Entrar" })).toBeInTheDocument();
  });
});
