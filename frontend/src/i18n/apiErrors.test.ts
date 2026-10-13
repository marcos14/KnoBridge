import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import { apiErrorKey, translateApiError, translateApiErrorCode } from "./apiErrors";
import { i18n } from "./index";

describe("apiErrorKey", () => {
  it("test_api_error_key_uses_known_api_code", () => {
    expect(apiErrorKey(new ApiError(401, "invalid_credentials"))).toBe(
      "apiErrors.invalid_credentials",
    );
  });

  it("test_api_error_key_falls_back_to_unknown_for_unmapped_code", () => {
    expect(apiErrorKey(new ApiError(418, "teapot"))).toBe("apiErrors.unknown");
  });

  it("test_api_error_key_falls_back_to_unknown_without_code", () => {
    expect(apiErrorKey(new ApiError(500))).toBe("apiErrors.unknown");
  });

  it("test_api_error_key_does_not_trust_inherited_properties", () => {
    expect(apiErrorKey(new ApiError(400, "toString"))).toBe("apiErrors.unknown");
  });

  it("test_api_error_key_maps_failed_fetch_to_network", () => {
    expect(apiErrorKey(new TypeError("Failed to fetch"))).toBe("apiErrors.network");
  });

  it("test_api_error_key_maps_anything_else_to_unknown", () => {
    expect(apiErrorKey(new Error("boom"))).toBe("apiErrors.unknown");
    expect(apiErrorKey("boom")).toBe("apiErrors.unknown");
  });
});

describe("translateApiError", () => {
  it("test_translate_api_error_returns_pt_br_message", () => {
    const t = i18n.t.bind(i18n);

    expect(translateApiError(new ApiError(401, "invalid_credentials"), t)).toBe(
      "E-mail ou senha incorretos.",
    );
    expect(translateApiError(new TypeError("Failed to fetch"), t)).toBe(
      "Não foi possível falar com o servidor. Verifique a conexão.",
    );
  });

  it("test_translate_api_error_explains_provider_in_use", () => {
    const t = i18n.t.bind(i18n);

    expect(translateApiError(new ApiError(409, "provider_in_use"), t)).toBe(
      "Esta credencial está em uso por uma coleção ou por um nível de resposta. Troque a credencial onde ela é usada antes de excluí-la.",
    );
    expect(translateApiError(new ApiError(422, "assistant_provider_invalid"), t)).toBe(
      "Escolha um provedor de LLM cadastrado neste workspace.",
    );
  });

  it("test_translate_api_error_explains_chat_errors", () => {
    const t = i18n.t.bind(i18n);
    const codes = [
      "assistant_inactive",
      "chat_failed",
      "feedback_target_invalid",
      "provider_auth_failed",
      "provider_rate_limited",
      "provider_request_failed",
      "provider_unavailable",
    ];

    for (const code of codes) {
      expect(apiErrorKey(new ApiError(409, code))).toBe(`apiErrors.${code}`);
    }
    expect(translateApiError(new ApiError(409, "assistant_inactive"), t)).toBe(
      "Este assistente está inativo e não aceita novas mensagens.",
    );
  });
});

describe("translateApiError for search", () => {
  it("test_translate_api_error_explains_embedding_errors", () => {
    const t = i18n.t.bind(i18n);
    const codes = [
      "embedding_dimension_mismatch",
      "embedding_invalid_response",
      "provider_embeddings_unsupported",
    ];

    for (const code of codes) {
      expect(apiErrorKey(new ApiError(502, code))).toBe(`apiErrors.${code}`);
    }
    expect(translateApiError(new ApiError(422, "provider_embeddings_unsupported"), t)).toBe(
      "Este provedor não oferece embeddings. Use uma credencial da OpenAI ou do OpenRouter na coleção.",
    );
  });
});

describe("translateApiErrorCode", () => {
  it("test_translate_api_error_code_returns_known_message", () => {
    const t = i18n.t.bind(i18n);

    expect(translateApiErrorCode("provider_auth_failed", t)).toBe(
      "O provedor de LLM recusou a chave de API. Confira a credencial.",
    );
    expect(translateApiErrorCode("provider_name_taken", t)).toBe(
      "Já existe um provedor com este nome no workspace.",
    );
  });

  it("test_translate_api_error_code_falls_back_to_unknown", () => {
    const t = i18n.t.bind(i18n);

    expect(translateApiErrorCode("teapot", t)).toBe("Algo deu errado. Tente novamente.");
  });
});
