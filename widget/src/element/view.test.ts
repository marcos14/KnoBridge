import { afterEach, describe, expect, it, vi } from "vitest";

import { CONFIG } from "../test/fake-api.ts";
import { resolveView, type AppearanceAttributes } from "./view.ts";

const NONE: AppearanceAttributes = {
  mode: null,
  position: null,
  theme: null,
  primaryColor: null,
  chatTitle: null,
  greeting: null,
  placeholder: null,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("resolveView", () => {
  it("test_resolve_view_uses_the_panel_configuration", () => {
    expect(resolveView(NONE, CONFIG)).toEqual({
      mode: "bubble",
      position: "bottom-right",
      theme: "auto",
      primary: "#2563eb",
      title: "Ajuda do ERP",
      greeting: "Olá! Como posso ajudar?",
      placeholder: "Escreva sua pergunta",
      maxChars: 8000,
    });
  });

  it("test_resolve_view_lets_valid_attributes_win", () => {
    const view = resolveView(
      {
        mode: "inline",
        position: "bottom-left",
        theme: "dark",
        primaryColor: "#FF0000",
        chatTitle: "Suporte",
        greeting: "",
        placeholder: "Pergunte",
      },
      CONFIG,
    );

    expect(view).toMatchObject({
      mode: "inline",
      position: "bottom-left",
      theme: "dark",
      primary: "#ff0000",
      title: "Suporte",
      greeting: "",
      placeholder: "Pergunte",
    });
  });

  it("test_resolve_view_ignores_invalid_attributes", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);

    const view = resolveView(
      { ...NONE, mode: "modal", position: "top", theme: "neon", primaryColor: "blue" },
      CONFIG,
    );

    expect(view).toMatchObject({
      mode: "bubble",
      position: "bottom-right",
      theme: "auto",
      primary: "#2563eb",
    });
  });

  it("test_resolve_view_has_defaults_without_configuration", () => {
    expect(resolveView(NONE, null)).toMatchObject({
      mode: "bubble",
      theme: "auto",
      primary: "#2563eb",
      maxChars: 8000,
    });
  });
});
