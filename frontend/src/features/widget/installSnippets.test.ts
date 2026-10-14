import { describe, expect, it } from "vitest";

import {
  identityElementSnippet,
  identityNodeSnippet,
  identityPythonSnippet,
  installSnippet,
  SIGNING_SECRET_VARIABLE,
  widgetScriptUrl,
} from "./installSnippets";

const KEY = "kbp_3k9x2m4q7w8e1r5t6y0u2i4o";

describe("installSnippets", () => {
  it("test_widget_script_url_drops_trailing_slashes", () => {
    expect(widgetScriptUrl("https://kb.empresa.com/")).toBe(
      "https://kb.empresa.com/widget/v1/knobridge-chat.js",
    );
  });

  it("test_install_snippet_in_bubble_mode", () => {
    expect(installSnippet("https://kb.empresa.com", KEY, "bubble")).toBe(
      [
        '<script src="https://kb.empresa.com/widget/v1/knobridge-chat.js" defer></script>',
        `<knobridge-chat widget-key="${KEY}"></knobridge-chat>`,
      ].join("\n"),
    );
  });

  it("test_install_snippet_in_inline_mode_has_a_height", () => {
    expect(installSnippet("https://kb.empresa.com", KEY, "inline")).toContain(
      `<knobridge-chat widget-key="${KEY}" mode="inline" style="height: 600px"></knobridge-chat>`,
    );
  });

  it("test_identity_snippets_read_the_secret_from_the_environment", () => {
    expect(identityElementSnippet(KEY)).toContain(`widget-key="${KEY}" identity=`);
    expect(identityPythonSnippet()).toContain(`os.environ["${SIGNING_SECRET_VARIABLE}"]`);
    expect(identityNodeSnippet()).toContain(`process.env.${SIGNING_SECRET_VARIABLE}`);
    expect(identityNodeSnippet()).toContain("return `v1.${payload}.${signature}`;");
    expect(identityPythonSnippet()).not.toContain("kbs_teste");
  });
});
