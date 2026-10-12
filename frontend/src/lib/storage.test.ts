import { afterEach, describe, expect, it, vi } from "vitest";

import { readStoredItem, removeStoredItem, writeStoredItem } from "./storage";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("storage", () => {
  it("test_storage_writes_and_reads_item", () => {
    writeStoredItem("knobridge-test", "value");

    expect(readStoredItem("knobridge-test")).toBe("value");
  });

  it("test_storage_read_returns_undefined_for_missing_item", () => {
    expect(readStoredItem("knobridge-missing")).toBeUndefined();
  });

  it("test_storage_read_returns_undefined_when_storage_throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(readStoredItem("knobridge-test")).toBeUndefined();
  });

  it("test_storage_session_area_is_separate_from_local", () => {
    writeStoredItem("knobridge-test", "tab", "session");

    expect(readStoredItem("knobridge-test", "session")).toBe("tab");
    expect(window.sessionStorage.getItem("knobridge-test")).toBe("tab");
    expect(readStoredItem("knobridge-test")).toBeUndefined();
  });

  it("test_storage_remove_forgets_item", () => {
    writeStoredItem("knobridge-test", "tab", "session");

    removeStoredItem("knobridge-test", "session");

    expect(readStoredItem("knobridge-test", "session")).toBeUndefined();
  });

  it("test_storage_remove_ignores_storage_failure", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => {
      removeStoredItem("knobridge-test");
    }).not.toThrow();
  });

  it("test_storage_write_ignores_storage_failure", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });

    expect(() => {
      writeStoredItem("knobridge-test", "value");
    }).not.toThrow();
  });
});
