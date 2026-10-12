import { describe, expect, it } from "vitest";

import { createQueryClient, DEFAULT_STALE_TIME_MS } from "./queryClient";

describe("createQueryClient", () => {
  it("test_create_query_client_applies_defaults", () => {
    const client = createQueryClient();
    const { queries, mutations } = client.getDefaultOptions();

    expect(queries?.staleTime).toBe(DEFAULT_STALE_TIME_MS);
    expect(queries?.retry).toBe(1);
    expect(queries?.refetchOnWindowFocus).toBe(false);
    expect(mutations?.retry).toBe(0);
  });

  it("test_create_query_client_returns_a_new_instance_each_call", () => {
    expect(createQueryClient()).not.toBe(createQueryClient());
  });
});
