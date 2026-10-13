import type { ApiKey } from "@/lib/api/apiKeys";

import { PRODUCT_ID, USER_ID } from "./factories";

export const API_KEY_ID = "00000000-0000-4000-8000-0000000003a1";
export const SCOPED_API_KEY_ID = "00000000-0000-4000-8000-0000000003a2";
export const REVOKED_API_KEY_ID = "00000000-0000-4000-8000-0000000003a3";
/** A key in the real format (`kbk_<8>_<43>`), synthetic. */
export const API_KEY_SECRET = "kbk_ab12cd34_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

/**
 * One item of `GET .../api-keys`: by default "portal-cliente", every assistant, created by Ana
 * and used one hour before `TEST_NOW`.
 */
export function makeApiKey(overrides: Partial<ApiKey> = {}): ApiKey {
  return {
    id: API_KEY_ID,
    name: "portal-cliente",
    key_prefix: "pc12ab34",
    product_ids: null,
    max_level: "product_dev",
    created_by: USER_ID,
    created_by_name: "Ana Teste",
    created_at: "2026-10-01T10:00:00Z",
    last_used_at: "2026-10-10T11:00:00Z",
    revoked_at: null,
    ...overrides,
  };
}

/**
 * The default keys, by name: antiga (revoked), integracao-erp (only Suporte ERP, never used,
 * creator deleted) and portal-cliente (every assistant).
 */
export function makeApiKeys(): ApiKey[] {
  return [
    makeApiKey({
      id: REVOKED_API_KEY_ID,
      name: "antiga",
      key_prefix: "zz99yy88",
      revoked_at: "2026-10-05T10:00:00Z",
    }),
    makeApiKey({
      id: SCOPED_API_KEY_ID,
      name: "integracao-erp",
      key_prefix: "ie56cd78",
      product_ids: [PRODUCT_ID],
      created_by: null,
      created_by_name: null,
      last_used_at: null,
    }),
    makeApiKey(),
  ];
}
