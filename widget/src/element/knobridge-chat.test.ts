import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../index.ts";
import { resetMemoryStorage } from "../lib/storage.ts";
import { create, find, mount, press, rendered, root, text } from "../test/dom.ts";
import { apiError, CONFIG, installFetch, json } from "../test/fake-api.ts";
import { setScriptOrigin } from "./knobridge-chat.ts";

beforeEach(() => {
  localStorage.clear();
  resetMemoryStorage();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  setScriptOrigin(null);
});

describe("<knobridge-chat> bubble mode", () => {
  it("test_bubble_renders_a_closed_launcher_and_hidden_dialog", async () => {
    installFetch({ "GET /config": json(CONFIG) });

    const { el, events } = await mount();

    const launcher = find(el, ".launcher");
    const panel = find(el, "[role=dialog]");
    expect(launcher.getAttribute("aria-label")).toBe("Abrir chat de ajuda");
    expect(launcher.getAttribute("aria-expanded")).toBe("false");
    expect(launcher.getAttribute("aria-controls")).toBe("panel");
    expect(panel.id).toBe("panel");
    expect(panel.hidden).toBe(true);
    expect(panel.getAttribute("aria-modal")).toBe("false");
    expect(find(el, "#title").textContent).toBe("Ajuda do ERP");
    expect(text(el)).toContain("Olá! Como posso ajudar?");
    expect(events[0]).toEqual({
      name: "knobridge-ready",
      detail: { mode: "bubble", ticketEnabled: true, feedbackEnabled: true },
    });
  });

  it("test_bubble_opens_by_keyboard_and_focuses_the_question", async () => {
    installFetch({ "GET /config": json(CONFIG) });
    const { el, events } = await mount();
    const launcher = find(el, ".launcher");
    launcher.focus();

    launcher.click(); // Enter or Space on a focused <button> activates it
    await el.updateComplete;
    await el.updateComplete;

    expect(find(el, "[role=dialog]").hidden).toBe(false);
    expect(launcher.getAttribute("aria-expanded")).toBe("true");
    expect(launcher.getAttribute("aria-label")).toBe("Fechar chat de ajuda");
    expect(el.hasAttribute("open")).toBe(true);
    expect(root(el).activeElement).toBe(find(el, "textarea"));
    expect(events.map((event) => event.name)).toContain("knobridge-open");
  });

  it("test_bubble_escape_closes_and_returns_focus_to_the_launcher", async () => {
    installFetch({ "GET /config": json(CONFIG) });
    const { el, events } = await mount({ open: "" });
    find(el, "textarea").focus();

    press(find(el, "textarea"), "Escape");
    await el.updateComplete;

    expect(find(el, "[role=dialog]").hidden).toBe(true);
    expect(el.hasAttribute("open")).toBe(false);
    expect(root(el).activeElement).toBe(find(el, ".launcher"));
    expect(events.map((event) => event.name)).toEqual(["knobridge-ready", "knobridge-close"]);
  });

  it("test_bubble_ignores_other_keys_on_the_panel", async () => {
    installFetch({ "GET /config": json(CONFIG) });
    const { el } = await mount({ open: "" });

    press(find(el, "[role=dialog]"), "a");
    await el.updateComplete;

    expect(el.isOpen).toBe(true);
  });

  it("test_bubble_close_button_and_methods", async () => {
    installFetch({ "GET /config": json(CONFIG) });
    const { el, events } = await mount();

    el.toggle();
    await el.updateComplete;
    expect(el.isOpen).toBe(true);
    [...root(el).querySelectorAll("header button")].at(-1)?.dispatchEvent(new MouseEvent("click"));
    await el.updateComplete;
    expect(el.isOpen).toBe(false);
    el.open();
    await el.updateComplete;
    el.toggle();
    await el.updateComplete;
    el.close(); // already closed: nothing happens

    expect(el.isOpen).toBe(false);
    expect(events.filter((event) => event.name !== "knobridge-ready").map((e) => e.name)).toEqual([
      "knobridge-open",
      "knobridge-close",
      "knobridge-open",
      "knobridge-close",
    ]);
  });

  it("test_bubble_programmatic_close_keeps_the_page_focus", async () => {
    installFetch({ "GET /config": json(CONFIG) });
    const { el } = await mount({ open: "" });
    const outside = document.createElement("button");
    document.body.append(outside);
    outside.focus();

    el.close();
    await el.updateComplete;

    expect(document.activeElement).toBe(outside);
  });

  it("test_bubble_left_position_and_appearance_attributes", async () => {
    installFetch({ "GET /config": json(CONFIG) });

    const { el } = await mount({
      position: "bottom-left",
      theme: "dark",
      "primary-color": "#FDE047",
      title: "Suporte",
      greeting: "",
      placeholder: "Pergunte aqui",
    });

    const container = find(el, ".root");
    expect(container.className).toBe("root bubble dark left");
    expect(container.style.getPropertyValue("--kb-primary")).toBe("#fde047");
    expect(container.style.getPropertyValue("--kb-primary-contrast")).toBe("#000000");
    expect(find(el, "#title").textContent).toBe("Suporte");
    expect(find(el, "textarea").getAttribute("placeholder")).toBe("Pergunte aqui");
    expect(text(el)).not.toContain("Como posso ajudar");
  });

  it("test_attributes_changed_later_update_the_view", async () => {
    installFetch({ "GET /config": json(CONFIG) });
    const { el } = await mount();

    el.setAttribute("theme", "light");
    await el.updateComplete;

    expect(find(el, ".root").className).toBe("root bubble light right");
  });
});

describe("<knobridge-chat> inline mode", () => {
  it("test_inline_renders_the_panel_without_launcher", async () => {
    installFetch({ "GET /config": json(CONFIG) });

    const { el, events } = await mount({ mode: "inline" });
    el.open();
    await el.updateComplete;

    expect(root(el).querySelector(".launcher")).toBeNull();
    expect(find(el, "[role=dialog]").hidden).toBe(false);
    expect(root(el).querySelectorAll("header button")).toHaveLength(1);
    expect(el.isOpen).toBe(false);
    expect(events[0]?.detail.mode).toBe("inline");
  });

  it("test_inline_from_the_panel_configuration_ignores_escape", async () => {
    installFetch({ "GET /config": json({ ...CONFIG, mode: "inline", theme: "light" }) });
    const { el } = await mount();

    press(find(el, "textarea"), "Escape");
    el.close();
    await el.updateComplete;

    expect(find(el, ".root").className).toBe("root inline light right");
    expect(find(el, "[role=dialog]").hidden).toBe(false);
  });
});

describe("<knobridge-chat> configuration", () => {
  it("test_missing_widget_key_renders_nothing_and_reports", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { el, events } = create({ "widget-key": "kbp_invalid" });

    document.body.append(el);
    await el.updateComplete;

    expect(rendered(el)).toHaveLength(0);
    expect(events).toEqual([
      { name: "knobridge-error", detail: { code: "widget_key_missing", status: null } },
    ]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("test_config_failure_hides_the_bubble", async () => {
    installFetch({ "GET /config": apiError(404, "widget_unavailable") });
    const { el, events } = create();

    document.body.append(el);
    await vi.waitFor(() => {
      expect(events).toHaveLength(1);
    });
    await el.updateComplete;

    expect(events[0]).toEqual({
      name: "knobridge-error",
      detail: { code: "widget_unavailable", status: 404 },
    });
    expect(root(el).querySelector(".launcher")).toBeNull();
  });

  it("test_config_failure_inline_says_unavailable", async () => {
    installFetch({ "GET /config": new TypeError("offline") });
    const { el, events } = create({ mode: "inline" });

    document.body.append(el);
    await vi.waitFor(() => {
      expect(events).toHaveLength(1);
    });
    await el.updateComplete;

    expect(find(el, "[role=status]").textContent).toBe("Chat indisponível no momento.");
    expect(events[0]?.detail).toEqual({ code: "network_error", status: null });
  });

  it("test_open_before_the_configuration_is_harmless", () => {
    installFetch({ "GET /config": () => new Promise<Response>(() => undefined) });
    const { el } = create();
    document.body.append(el);

    el.open();

    expect(el.isOpen).toBe(true);
  });

  it("test_api_base_defaults_to_the_script_origin_then_the_page", async () => {
    const { calls } = installFetch({ "GET /config": json(CONFIG) });
    setScriptOrigin("https://cdn.example.com");

    await mount({ "api-base": "" });
    const { el } = create({ "api-base": "" });
    el.removeAttribute("api-base");
    setScriptOrigin(null);
    document.body.append(el);
    await vi.waitFor(() => {
      expect(calls).toHaveLength(2);
    });

    expect(calls[0]?.url).toMatch(/^https:\/\/cdn\.example\.com\/v1\/widget\//);
    expect(calls[1]?.url).toMatch(new RegExp(`^${location.origin}/v1/widget/`));
  });

  it("test_reconnecting_keeps_the_element_state", async () => {
    const { calls } = installFetch({ "GET /config": json(CONFIG) });
    const { el } = await mount();

    el.remove();
    document.body.append(el);
    await el.updateComplete;

    expect(calls).toHaveLength(1);
    expect(find(el, ".launcher")).toBeTruthy();
  });
});
