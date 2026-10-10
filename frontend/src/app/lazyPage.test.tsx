import { act, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";

import { lazyPage, preloadLazyPages } from "./lazyPage";

function deferredPage() {
  let resolve!: () => void;
  const ready = new Promise<void>((done) => {
    resolve = done;
  });
  const Page = () => <h1>Página carregada</h1>;
  const element = lazyPage(async () => {
    await ready;
    return Page;
  });
  return { element, resolve };
}

describe("lazyPage", () => {
  it("test_lazy_page_shows_status_until_the_code_arrives", async () => {
    const { element, resolve } = deferredPage();
    render(<I18nextProvider i18n={i18n}>{element}</I18nextProvider>);

    expect(screen.getByRole("status")).toHaveTextContent("Carregando a página…");
    await act(async () => {
      resolve();
      await Promise.resolve();
    });

    expect(await screen.findByRole("heading", { name: "Página carregada" })).toBeVisible();
  });

  it("test_lazy_page_preloaded_renders_at_once", async () => {
    const { element, resolve } = deferredPage();
    resolve();
    await preloadLazyPages();

    render(<I18nextProvider i18n={i18n}>{element}</I18nextProvider>);

    expect(screen.getByRole("heading", { name: "Página carregada" })).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
