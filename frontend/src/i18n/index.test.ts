import { describe, expect, it } from "vitest";

import { i18n } from "./index";

describe("i18n", () => {
  it("test_i18n_uses_pt_br_by_default", () => {
    expect(i18n.language).toBe("pt-BR");
    expect(i18n.t("app.title")).toBe("KnoBridge");
    expect(i18n.t("notFound.title")).toBe("Página não encontrada");
  });

  it("test_i18n_missing_key_returns_the_key", () => {
    // Keys are typed against pt-BR.json; widening is the only way to ask for one that does not exist.
    const translate = i18n.t.bind(i18n) as (key: string) => string;

    expect(translate("missing.key")).toBe("missing.key");
  });
});
