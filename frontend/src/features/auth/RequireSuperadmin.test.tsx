import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { makeMe } from "@/test/factories";
import { meAs } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { RequireSuperadmin } from "./RequireSuperadmin";

describe("RequireSuperadmin", () => {
  it("test_require_superadmin_lets_superadmin_through", async () => {
    server.use(meAs(makeMe({ is_superadmin: true })));
    renderWithProviders({ path: "/admin/users" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Usuários da instância" }),
    ).toBeInTheDocument();
  });

  it("test_require_superadmin_shows_403_for_regular_user", async () => {
    renderWithProviders({ path: "/admin" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Acesso negado" }),
    ).toBeInTheDocument();
  });

  it("test_require_superadmin_shows_403_while_session_is_unknown", () => {
    server.use(
      http.get("*/v1/me", async () => {
        await delay("infinite");
        return HttpResponse.json(null);
      }),
    );
    renderWithProviders({
      path: "/admin",
      routes: [{ path: "/admin", element: <RequireSuperadmin /> }],
    });

    expect(screen.getByRole("heading", { level: 1, name: "Acesso negado" })).toBeInTheDocument();
  });
});
