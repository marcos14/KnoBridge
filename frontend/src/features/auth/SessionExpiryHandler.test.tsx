import { act, screen } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { meQueryKey } from "@/lib/api/auth";
import { apiClient } from "@/lib/api/client";
import { WORKSPACE_ID } from "@/test/factories";
import { apiErrorResponse } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

const expiredSession = [
  http.get("*/v1/me/sessions", () => apiErrorResponse(401, "unauthenticated")),
  http.get("*/v1/me", () => apiErrorResponse(401, "unauthenticated")),
];

describe("SessionExpiryHandler", () => {
  it("test_session_expiry_redirects_to_login_preserving_destination", async () => {
    const destination = `/w/${WORKSPACE_ID}?tab=sources`;
    const { router, queryClient } = renderWithProviders({ path: destination });
    await screen.findByRole("heading", { level: 1, name: "Início" });
    server.use(...expiredSession);

    await act(() => apiClient.GET("/v1/me/sessions"));

    expect(await screen.findByRole("heading", { level: 1, name: "Entrar" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(destination);
    expect(queryClient.getQueryData(meQueryKey)).toBeNull();
  });

  it("test_session_expiry_on_login_page_stays_there", async () => {
    const { router } = renderWithProviders({ path: "/login" });
    await screen.findByRole("heading", { level: 1, name: "Entrar" });
    server.use(...expiredSession);

    await act(() => apiClient.GET("/v1/me/sessions"));

    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("");
  });
});
