import type { TFunction } from "i18next";

/** Someone who may appear as the author of an audit event. */
export interface AuditActor {
  id: string;
  name: string;
}

/**
 * Who did it, for reading: the person's name when known, "Sistema" for events without an actor
 * (setup, background work) and the raw id for someone not listed (a removed member).
 */
export function actorLabel(
  actorUserId: string | null,
  actors: readonly AuditActor[],
  t: TFunction,
): string {
  if (actorUserId === null) {
    return t("audit.system");
  }
  const actor = actors.find((item) => item.id === actorUserId);
  return actor?.name ?? t("audit.unknownActor", { id: actorUserId });
}
