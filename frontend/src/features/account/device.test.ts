import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";

import { deviceLabel } from "./device";

describe("deviceLabel", () => {
  it.each([
    [{ browser: "Chrome", os: "Windows" }, "Chrome no Windows"],
    [{ browser: "Firefox", os: null }, "Firefox"],
    [{ browser: null, os: "Linux" }, "Navegador no Linux"],
    [{ browser: null, os: null }, "Dispositivo desconhecido"],
  ])("test_device_label_%o_is_%s", (summary, expected) => {
    expect(deviceLabel(summary, i18n.t)).toBe(expected);
  });
});
