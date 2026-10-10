import type { TFunction } from "i18next";

import ptBR from "./locales/pt-BR.json";

type AuditActionKey = keyof (typeof ptBR)["auditActions"];

/**
 * Key of an action under `auditActions` in the locale files: the API code with its dots turned
 * into `_`, because i18next reads dots as nesting (`auth.login.failed` → `auth_login_failed`).
 */
function auditActionKey(action: string): string {
  return action.replaceAll(".", "_");
}

function isKnownKey(key: string): key is AuditActionKey {
  return Object.hasOwn(ptBR.auditActions, key);
}

/**
 * Label of an audit action in the interface language, or the raw code when the interface does
 * not know it yet (an action added to the backend after this build).
 */
export function auditActionLabel(action: string, t: TFunction): string {
  const key = auditActionKey(action);
  return isKnownKey(key) ? t(`auditActions.${key}`) : action;
}
