/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the KnoBridge API. Defaults to "/" (same origin, proxied to the API). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
