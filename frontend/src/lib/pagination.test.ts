import { describe, expect, it } from "vitest";

import { clampOffset, pageOf, pageRange, parseOffset } from "./pagination";

describe("pageRange", () => {
  it("test_page_range_first_page", () => {
    expect(pageRange(0, 20, 45)).toEqual({ from: 1, to: 20 });
  });

  it("test_page_range_last_page_stops_at_total", () => {
    expect(pageRange(40, 20, 45)).toEqual({ from: 41, to: 45 });
  });

  it("test_page_range_empty_list", () => {
    expect(pageRange(0, 20, 0)).toEqual({ from: 0, to: 0 });
  });
});

describe("clampOffset", () => {
  it("test_clamp_offset_keeps_valid_offset", () => {
    expect(clampOffset(20, 20, 45)).toBe(20);
  });

  it("test_clamp_offset_moves_to_last_page_when_past_end", () => {
    expect(clampOffset(40, 20, 40)).toBe(20);
    expect(clampOffset(60, 20, 45)).toBe(40);
  });

  it("test_clamp_offset_empty_list_is_zero", () => {
    expect(clampOffset(20, 20, 0)).toBe(0);
  });
});

describe("pageOf", () => {
  it("test_page_of_slices_rows", () => {
    expect(pageOf([1, 2, 3, 4, 5], 2, 2)).toEqual([3, 4]);
  });
});

describe("parseOffset", () => {
  it("test_parse_offset_accepts_only_positive_integers", () => {
    expect(parseOffset("40")).toBe(40);
    expect(parseOffset(null)).toBe(0);
    expect(parseOffset("-20")).toBe(0);
    expect(parseOffset("2.5")).toBe(0);
    expect(parseOffset("abc")).toBe(0);
  });
});
