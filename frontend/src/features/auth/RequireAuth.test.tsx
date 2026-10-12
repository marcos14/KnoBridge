import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WORKSPACE_ID } from "@/test/factories";
import { meOk, meServerError, meUnauthenticated } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

describe("RequireAuth", () => {
  it("test_require_auth_redirects_anonymous_user_to_login_preserving_destination", async () => {
    server.use(meUnauthenticated);
    const destination = `/w/${WORKSPACE_ID}/settings/members?tab=pending`;
    const { router } = renderWithProviders({ path: destination });

    expect(await screen.findByRole("heading", { level: 1, name: "Entrar" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(destination);
  });

  it("test_require_auth_lets_logged_in_user_through", async () => {
    renderWithProviders({ path: "/account/profile" });

    expect(await screen.findByRole("heading", { level: 1, name: "Perfil" })).toBeInTheDocument();
  });

  it("test_require_auth_does_not_guard_public_routes", async () => {
    server.use(meUnauthenticated);
    const { router } = renderWithProviders({ path: "/reset-password?token=abc" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Redefinir senha" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/reset-password");
  });

  it("test_require_auth_offers_retry_when_session_cannot_be_loaded", async () => {
    const user = userEvent.setup();
    server.use(meServerError);
    renderWithProviders({ path: "/account" });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    server.use(meOk);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Perfil" })).toBeInTheDocument();
  });
});
