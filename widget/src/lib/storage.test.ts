import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TOKEN } from "../test/fake-api.ts";
import { ConversationStore, resetMemoryStorage, type StoredConversation } from "./storage.ts";

const KEY = "kbp_3k9x2m4q7w8e1r5t6y0u2i4o";
const ENTRY: StoredConversation = {
  conversation_id: "c1",
  visitor_token: TOKEN,
  identity_sub: null,
  saved_at: "2026-10-14T10:00:00.000Z",
};

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  resetMemoryStorage();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ConversationStore", () => {
  it("test_store_saves_only_the_pointer_in_local_storage", () => {
    new ConversationStore("local", KEY).save(ENTRY);

    expect(JSON.parse(localStorage.getItem(`knobridge:v1:${KEY}`) ?? "")).toEqual(ENTRY);
    expect(new ConversationStore("local", KEY).load()).toEqual(ENTRY);
  });

  it("test_store_session_uses_session_storage", () => {
    new ConversationStore("session", KEY).save({ ...ENTRY, identity_sub: "cliente-42" });

    expect(sessionStorage.getItem(`knobridge:v1:${KEY}`)).not.toBeNull();
    expect(localStorage.length).toBe(0);
    expect(new ConversationStore("session", KEY).load()?.identity_sub).toBe("cliente-42");
  });

  it("test_store_none_keeps_the_pointer_in_memory_only", () => {
    new ConversationStore("none", KEY).save(ENTRY);

    expect(localStorage.length).toBe(0);
    expect(new ConversationStore("none", KEY).load()).toEqual(ENTRY);
    new ConversationStore("none", KEY).clear();
    expect(new ConversationStore("none", KEY).load()).toBeNull();
  });

  it("test_store_clear_removes_the_entry", () => {
    const store = new ConversationStore("local", KEY);
    store.save(ENTRY);

    store.clear();

    expect(store.load()).toBeNull();
  });

  it.each([
    ["not json", "{"],
    ["null", "null"],
    ["bad token", JSON.stringify({ ...ENTRY, visitor_token: "kbv_short" })],
    ["bad sub", JSON.stringify({ ...ENTRY, identity_sub: 42 })],
    ["no date", JSON.stringify({ ...ENTRY, saved_at: undefined })],
    ["no id", JSON.stringify({ ...ENTRY, conversation_id: 1 })],
    ["no token", JSON.stringify({ ...ENTRY, visitor_token: 1 })],
  ])("test_store_drops_a_corrupted_entry_%s", (_name, raw) => {
    localStorage.setItem(`knobridge:v1:${KEY}`, raw);

    expect(new ConversationStore("local", KEY).load()).toBeNull();
    expect(localStorage.getItem(`knobridge:v1:${KEY}`)).toBeNull();
  });

  it("test_store_falls_back_to_memory_when_storage_throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const store = new ConversationStore("local", KEY);

    store.save(ENTRY);
    expect(store.load()).toEqual(ENTRY);
    store.clear();
    expect(store.load()).toBeNull();
  });

  it("test_store_falls_back_to_memory_when_the_storage_getter_throws", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const store = new ConversationStore("local", KEY);

    store.save(ENTRY);

    expect(store.load()).toEqual(ENTRY);
  });
});
