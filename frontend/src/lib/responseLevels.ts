import type { TFunction } from "i18next";

import type { Role } from "@/lib/api/auth";
import { RESPONSE_LEVELS, type ResponseLevel } from "@/lib/api/levels";
import type { SourceKind } from "@/lib/api/sources";

/** Order of the levels (`level_rank` of `docs/specs/produtos-e-niveis.md`). */
const LEVEL_RANK: Record<ResponseLevel, number> = {
  end_user: 0,
  support: 1,
  product_dev: 2,
};

/** Whether `level` is above `other` (more technical). */
export function isLevelAbove(level: ResponseLevel, other: ResponseLevel): boolean {
  return LEVEL_RANK[level] > LEVEL_RANK[other];
}

/** The level named by `value` (the API's technical name), or `undefined` when it names none. */
export function parseLevel(value: string | null | undefined): ResponseLevel | undefined {
  return RESPONSE_LEVELS.find((level) => level === value);
}

/** The name people read for a level: "Usuário final", "Suporte", "Desenvolvimento e produto". */
export function levelLabel(level: ResponseLevel, t: TFunction): string {
  return t(`workspaceSettings.levels.names.${level}`);
}

/** Who a level is for and what its answers may carry, in one sentence. */
export function levelAudience(level: ResponseLevel, t: TFunction): string {
  return t(`workspaceSettings.levels.audiences.${level}`);
}

/**
 * A member's maximum level in a product when nothing is stored: `product_dev` for owners and
 * admins, `end_user` for editors and viewers (D11).
 */
export function defaultMaxLevel(role: Role): ResponseLevel {
  return role === "owner" || role === "admin" ? "product_dev" : "end_user";
}

/** Minimum level of a new source of `kind` when none is given ("Padrões por tipo"). */
const SOURCE_MIN_LEVELS: Record<SourceKind, ResponseLevel> = {
  folder: "end_user",
  runner: "end_user",
  tickets: "support",
  cards: "product_dev",
  git: "product_dev",
};

export function defaultSourceMinLevel(kind: SourceKind): ResponseLevel {
  return SOURCE_MIN_LEVELS[kind];
}
