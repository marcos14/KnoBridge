import type { TFunction } from "i18next";

import type { DeviceSummary } from "@/lib/userAgent";

/** How a session's device reads on screen: "Chrome no Windows", "Firefox", "Navegador no Linux". */
export function deviceLabel({ browser, os }: DeviceSummary, t: TFunction): string {
  if (browser !== null && os !== null) {
    return t("account.security.sessions.device", { browser, os });
  }
  if (browser !== null) {
    return browser;
  }
  if (os !== null) {
    return t("account.security.sessions.deviceOs", { os });
  }
  return t("account.security.sessions.unknownDevice");
}
