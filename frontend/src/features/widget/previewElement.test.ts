import { afterEach, describe, expect, it } from "vitest";

import { ensureWidgetScript, previewAttributes, WIDGET_SCRIPT_ID } from "./previewElement";

const APPEARANCE = {
  theme: "dark",
  primaryColor: " #AABBCC ",
  title: " Ajuda ",
  greeting: "Oi",
  placeholder: "Pergunte",
} as const;

describe("previewElement", () => {
  afterEach(() => {
    document.getElementById(WIDGET_SCRIPT_ID)?.remove();
  });

  it("test_ensure_widget_script_adds_the_script_once", () => {
    ensureWidgetScript("http://localhost:3000/widget/v1/knobridge-chat.js");
    ensureWidgetScript("http://localhost:3000/widget/v1/knobridge-chat.js");

    const scripts = document.head.querySelectorAll(`script#${WIDGET_SCRIPT_ID}`);
    expect(scripts).toHaveLength(1);
    expect(scripts[0]).toHaveAttribute("src", "http://localhost:3000/widget/v1/knobridge-chat.js");
  });

  it("test_preview_attributes_carry_the_appearance_being_edited", () => {
    expect(previewAttributes("http://localhost:3000", APPEARANCE)).toEqual({
      "api-base": "http://localhost:3000",
      mode: "inline",
      storage: "none",
      theme: "dark",
      "primary-color": "#aabbcc",
      title: "Ajuda",
      greeting: "Oi",
      placeholder: "Pergunte",
    });
  });

  it("test_preview_attributes_fall_back_to_the_saved_config_when_empty_or_invalid", () => {
    const attributes = previewAttributes("http://localhost:3000", {
      ...APPEARANCE,
      primaryColor: "azul",
      title: "",
      greeting: "",
      placeholder: " ",
    });

    expect(attributes["primary-color"]).toBeNull();
    expect(attributes.title).toBeNull();
    expect(attributes.placeholder).toBeNull();
    expect(attributes.greeting).toBe("");
  });
});
