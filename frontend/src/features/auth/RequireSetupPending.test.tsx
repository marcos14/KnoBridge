import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { setupStatusNeeded, setupStatusServerError } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

describe("RequireSetupPending", () => {
  it("test_require_setup_pending_shows_setup_on_fresh_instance", async () => {
    server.use(setupStatusNeeded);
    renderWithProviders({ path: "/setup" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Configuração inicial" }),
    ).toBeInTheDocument();
  });

  it("test_require_setup_pending_sends_done_instance_home", async () => {
    const { router } = renderWithProviders({ path: "/setup" });

    await waitFor(() => {
      expect(router.state.location.pathname).not.toBe("/setup");
    });
    expect(screen.queryByRole("heading", { name: "Configuração inicial" })).not.toBeInTheDocument();
  });

  it("test_require_setup_pending_offers_retry_when_status_fails", async () => {
    const user = userEvent.setup();
    server.use(setupStatusServerError);
    renderWithProviders({ path: "/setup" });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    server.use(setupStatusNeeded);
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Configuração inicial" }),
    ).toBeInTheDocument();
  });
});
