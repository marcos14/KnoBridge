import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import ptBR from "./locales/pt-BR.json";

export const defaultLanguage = "pt-BR";
export const defaultNamespace = "translation";

export const resources = {
  [defaultLanguage]: { [defaultNamespace]: ptBR },
} as const;

export const i18n = i18next.createInstance();

// Resources are bundled, so synchronous init guarantees translations on the first render.
void i18n.use(initReactI18next).init({
  resources,
  lng: defaultLanguage,
  fallbackLng: defaultLanguage,
  defaultNS: defaultNamespace,
  initAsync: false,
  interpolation: {
    // React already escapes rendered values.
    escapeValue: false,
  },
});
