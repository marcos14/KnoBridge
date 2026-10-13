import { describe, expect, it } from "vitest";

import { i18n } from "@/i18n";
import { ApiError } from "@/lib/api/client";

import { isWebhookUrl, webhookApiErrorText, webhookErrorText } from "./ticketWebhook";

const t = i18n.t.bind(i18n);

describe("isWebhookUrl", () => {
  it.each(["https://chamados.example.test/kb", " http://webhook-fake:8080/hook "])(
    "test_is_webhook_url_accepts_%s",
    (url) => {
      expect(isWebhookUrl(url)).toBe(true);
    },
  );

  it.each([
    "",
    "chamados.example.test/kb",
    "ftp://chamados.example.test/kb",
    "https://ana:segredo@chamados.example.test/kb",
    "https://token@chamados.example.test/kb",
  ])("test_is_webhook_url_rejects_%s", (url) => {
    expect(isWebhookUrl(url)).toBe(false);
  });
});

describe("webhookErrorText", () => {
  it("test_webhook_error_text_adds_the_reason", () => {
    expect(webhookErrorText("webhook_destination_blocked", { reason: "private" }, t)).toBe(
      "O destino do webhook não é permitido. Motivo: o host aponta para uma rede privada.",
    );
  });

  it("test_webhook_error_text_adds_the_http_status", () => {
    expect(webhookErrorText("webhook_rejected", { status: 500 }, t)).toBe(
      "O destino recusou o envio. O destino respondeu HTTP 500.",
    );
  });

  it.each([null, { reason: "desconhecido" }, "texto"])(
    "test_webhook_error_text_without_known_details_is_the_code_message_%#",
    (details) => {
      expect(webhookErrorText("webhook_unreachable", details, t)).toBe(
        "Não foi possível alcançar o destino do webhook.",
      );
    },
  );

  it("test_webhook_api_error_text_reads_api_errors_and_others", () => {
    const invalid = new ApiError(422, "webhook_url_invalid", { reason: "scheme_not_https" });

    expect(webhookApiErrorText(invalid, t)).toBe(
      "A URL do webhook é inválida. Motivo: a URL precisa usar https.",
    );
    expect(webhookApiErrorText(new TypeError("fetch failed"), t)).toBe(
      "Não foi possível falar com o servidor. Verifique a conexão.",
    );
  });
});
