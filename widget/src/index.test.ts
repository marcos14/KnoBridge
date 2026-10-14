import { describe, expect, it, vi } from "vitest";

import { KnoBridgeChat, originOf, register, TAG_NAME } from "./index.ts";

describe("entry point", () => {
  it("test_entry_registers_the_element_once", () => {
    const define = vi.spyOn(customElements, "define");

    register();

    expect(customElements.get(TAG_NAME)).toBe(KnoBridgeChat);
    expect(define).not.toHaveBeenCalled();
    define.mockRestore();
  });

  it("test_entry_registers_in_an_empty_registry", () => {
    const define = vi.fn();
    const registry = { get: vi.fn(() => undefined), define } as unknown as CustomElementRegistry;

    register(registry);

    expect(define).toHaveBeenCalledWith(TAG_NAME, KnoBridgeChat);
  });

  it("test_origin_of_reads_the_script_src", () => {
    const script = document.createElement("script");
    script.src = "https://kb.example.com/widget/v1/knobridge-chat.js";

    expect(originOf(script)).toBe("https://kb.example.com");
    expect(originOf(document.createElement("script"))).toBeNull();
    expect(originOf(document.createElement("div"))).toBeNull();
    expect(originOf(null)).toBeNull();
  });
});
