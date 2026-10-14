import type { Widget } from "@/lib/api/widgets";

import { OTHER_PRODUCT_ID, PRODUCT_ID, USER_ID } from "./factories";

export const WIDGET_ID = "00000000-0000-4000-8000-0000000000b1";
export const OTHER_WIDGET_ID = "00000000-0000-4000-8000-0000000000b2";

/** A synthetic `kbs_` signing secret (43 characters after the prefix), as the `POST` returns it. */
export const WIDGET_SECRET = "kbs_teste-NAO-use-em-producao-0123456789abcdefg";
export const WIDGET_SECRET_CREATED_AT = "2026-10-10T12:00:00Z";

/** The default widget: "Site público" of Suporte ERP, a bubble on two origins, no secret. */
export function makeWidget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: WIDGET_ID,
    product_id: PRODUCT_ID,
    product_name: "Suporte ERP",
    name: "Site público",
    public_key: "kbp_3k9x2m4q7w8e1r5t6y0u2i4o",
    allowed_origins: ["https://app.cliente.com.br", "https://*.cliente.com.br"],
    active: true,
    mode: "bubble",
    position: "bottom-right",
    theme: "auto",
    primary_color: "#2563eb",
    title: null,
    greeting: "Olá! Como posso ajudar?",
    placeholder: "Escreva sua pergunta",
    feedback_enabled: true,
    ticket_enabled: true,
    ticket_available: false,
    messages_per_ip_per_hour: 30,
    messages_per_day: 1000,
    signing_secret_configured: false,
    signing_secret_created_at: null,
    created_by: USER_ID,
    created_by_name: "Ana Teste",
    created_at: "2026-10-05T10:00:00Z",
    updated_at: "2026-10-05T10:00:00Z",
    ...overrides,
  };
}

/**
 * The default widgets, by name: "Portal interno" (Rascunho, inline, inactive, with a signing
 * secret and three origins) and "Site público".
 */
export function makeWidgets(): Widget[] {
  return [
    makeWidget({
      id: OTHER_WIDGET_ID,
      product_id: OTHER_PRODUCT_ID,
      product_name: "Rascunho",
      name: "Portal interno",
      public_key: "kbp_portal0interno0000000000",
      allowed_origins: [
        "https://portal.cliente.com.br",
        "http://intranet.cliente.local:8080",
        "https://erp.cliente.com.br",
      ],
      active: false,
      mode: "inline",
      theme: "dark",
      title: "Ajuda do portal",
      signing_secret_configured: true,
      signing_secret_created_at: "2026-10-06T09:00:00Z",
    }),
    makeWidget(),
  ];
}
