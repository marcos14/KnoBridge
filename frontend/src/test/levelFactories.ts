import type { ResponseLevel, WorkspaceLevel } from "@/lib/api/levels";
import type { MemberLevels, ProductRef } from "@/lib/api/memberLevels";
import { defaultMaxLevel } from "@/lib/responseLevels";

import { makeMembers, OTHER_PRODUCT_ID, PRODUCT_ID, PROVIDER_ID } from "./factories";

/** The products of the levels table, by name: Rascunho (inactive) and Suporte ERP. */
export function makeProductRefs(): ProductRef[] {
  return [
    { id: OTHER_PRODUCT_ID, name: "Rascunho", active: false },
    { id: PRODUCT_ID, name: "Suporte ERP", active: true },
  ];
}

/**
 * The member × product table for the default members (Ana owner, Bruno admin, Carla editor, Davi
 * viewer): everyone at the default of the role, except Carla, stored at `support` in Suporte ERP.
 */
export function makeMemberLevels(products: ProductRef[] = makeProductRefs()): MemberLevels[] {
  return makeMembers().map((member) => ({
    user_id: member.user_id,
    name: member.name,
    email: member.email,
    role: member.role,
    levels: products.map((product) =>
      member.role === "editor" && product.id === PRODUCT_ID
        ? { product_id: product.id, max_level: "support", explicit: true }
        : { product_id: product.id, max_level: defaultMaxLevel(member.role), explicit: false },
    ),
  }));
}

/** Synthetic default instructions of each level (the real texts live in the backend). */
export const DEFAULT_LEVEL_INSTRUCTIONS: Record<ResponseLevel, string> = {
  end_user: "Você atende o usuário final. Nunca mostre código.",
  support: "Você atende a equipe de suporte. SQL só de leitura.",
  product_dev: "Você atende desenvolvimento e produto.",
};

/**
 * One level of `GET .../levels`: by default `end_user` on OpenAI Produção with `gpt-4.1-mini`,
 * the default instructions and US$ 0,00256 per answer.
 */
export function makeWorkspaceLevel(overrides: Partial<WorkspaceLevel> = {}): WorkspaceLevel {
  const level = overrides.level ?? "end_user";
  return {
    level,
    provider_id: PROVIDER_ID,
    provider_name: "OpenAI Produção",
    provider_kind: "openai",
    model: "gpt-4.1-mini",
    temperature: 0.2,
    instructions: DEFAULT_LEVEL_INSTRUCTIONS[level],
    instructions_is_default: true,
    default_instructions: DEFAULT_LEVEL_INSTRUCTIONS[level],
    configured: true,
    price: { input_usd_per_mtok: 0.4, output_usd_per_mtok: 1.6 },
    estimated_cost_per_answer_usd: 0.00256,
    updated_at: "2026-10-13T10:00:00Z",
    max_steps: 2,
    estimated_max_cost_per_answer_usd: 0.00484,
    tools_supported: null,
    ...overrides,
  };
}

/** A level without credential and model (the chat in it does not work). */
export function makeUnconfiguredLevel(level: ResponseLevel): WorkspaceLevel {
  return makeWorkspaceLevel({
    level,
    provider_id: null,
    provider_name: null,
    provider_kind: null,
    model: null,
    configured: false,
    price: null,
    estimated_cost_per_answer_usd: null,
    estimated_max_cost_per_answer_usd: null,
  });
}

/**
 * The three levels with 2, 3 and 4 searches (Usuário final raised from its default of 1, to show
 * the cost with every search): Usuário final configured (US$ 0,00484 with both searches), Suporte with edited instructions and a model without price, Desenvolvimento
 * e produto not configured.
 */
export function makeWorkspaceLevels(): WorkspaceLevel[] {
  return [
    makeWorkspaceLevel(),
    makeWorkspaceLevel({
      level: "support",
      model: "modelo-sem-preco",
      temperature: 0.5,
      instructions: "Texto do suporte editado no workspace.",
      instructions_is_default: false,
      price: null,
      estimated_cost_per_answer_usd: null,
      estimated_max_cost_per_answer_usd: null,
      max_steps: 3,
    }),
    { ...makeUnconfiguredLevel("product_dev"), max_steps: 4 },
  ];
}
