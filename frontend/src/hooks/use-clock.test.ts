import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { systemClock, useClock } from "./use-clock";

describe("useClock", () => {
  it("test_use_clock_defaults_to_system_clock", () => {
    const { result } = renderHook(() => useClock());

    expect(result.current).toBe(systemClock);
    expect(result.current()).toBeInstanceOf(Date);
  });
});
