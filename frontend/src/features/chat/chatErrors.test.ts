import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { ApiError } from "@/lib/api/client";

import { chatErrorMessage } from "./chatErrors";

const t = i18n.t;

describe("chatErrorMessage", () => {
  it("test_chat_error_names_the_levels_of_a_level_not_allowed", () => {
    const error = new ApiError(403, "level_not_allowed", {
      requested_level: "product_dev",
      max_level: "support",
      reason: "member",
    });

    expect(chatErrorMessage(error, t)).toBe(
      "O seu nível máximo neste produto é Suporte e esta conversa está no nível Desenvolvimento e produto. Abra uma nova conversa num nível permitido.",
    );
  });

  it("test_chat_error_level_not_allowed_without_details_uses_the_generic_message", () => {
    for (const details of [null, "x", { requested_level: "support", max_level: 3 }]) {
      expect(chatErrorMessage(new ApiError(403, "level_not_allowed", details), t)).toBe(
        "O nível pedido está acima do nível máximo permitido.",
      );
    }
  });

  it("test_chat_error_level_not_configured_asks_for_an_admin", () => {
    expect(
      chatErrorMessage(new ApiError(409, "level_not_configured", { level: "support" }), t),
    ).toBe(
      "O nível Suporte ainda não foi configurado neste workspace: peça a um admin que escolha a credencial e o modelo dele em Configurações.",
    );
    expect(chatErrorMessage(new ApiError(409, "level_not_configured"), t)).toBe(
      "Este nível ainda não foi configurado neste workspace: peça a um admin que escolha a credencial e o modelo dele em Configurações.",
    );
  });

  it("test_chat_error_product_inactive", () => {
    expect(chatErrorMessage(new ApiError(409, "product_inactive"), t)).toBe(
      "Este produto foi desativado e não aceita novas conversas nem perguntas.",
    );
  });

  it("test_chat_error_other_codes_use_the_api_error_message", () => {
    expect(chatErrorMessage(new ApiError(404, "not_found"), t)).toBe(t("apiErrors.not_found"));
    expect(chatErrorMessage(new TypeError("offline"), t)).toBe(t("apiErrors.network"));
  });
});
