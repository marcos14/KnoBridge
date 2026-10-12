import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { healthReadyPending, healthReadyUnavailable } from "@/test/handlers";
import { renderWithProviders } from "@/test/renderWithProviders";
import { server } from "@/test/server";

import { ApiStatus } from "./ApiStatus";

function renderApiStatus() {
  return renderWithProviders({ routes: [{ path: "/", element: <ApiStatus /> }] });
}

describe("ApiStatus", () => {
  it("test_api_status_shows_ok_when_api_is_ready", async () => {
    renderApiStatus();

    expect(await screen.findByText("API: disponível")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("API: disponível");
  });

  it("test_api_status_shows_unavailable_when_api_fails", async () => {
    server.use(healthReadyUnavailable);
    renderApiStatus();

    expect(await screen.findByText("API: indisponível")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("API: indisponível");
  });

  it("test_api_status_shows_loading_while_waiting", () => {
    server.use(healthReadyPending);
    renderApiStatus();

    expect(screen.getByRole("status")).toHaveTextContent("API: verificando…");
  });
});
