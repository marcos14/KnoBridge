import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { createQueryClient } from "@/app/queryClient";
import { healthReadyNetworkError, healthReadyUnavailable } from "@/test/handlers";
import { server } from "@/test/server";

import { ApiError } from "./client";
import { useApiHealth } from "./health";

function renderUseApiHealth() {
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useApiHealth(), { wrapper });
}

describe("useApiHealth", () => {
  it("test_use_api_health_returns_ready_response", async () => {
    const { result } = renderUseApiHealth();

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual({ status: "ok", checks: { database: "ok" } });
  });

  it("test_use_api_health_fails_with_api_error_on_503", async () => {
    server.use(healthReadyUnavailable);
    const { result } = renderUseApiHealth();

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error).toMatchObject({ status: 503 });
  });

  it("test_use_api_health_fails_on_network_error", async () => {
    server.use(healthReadyNetworkError);
    const { result } = renderUseApiHealth();

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(TypeError);
  });
});
