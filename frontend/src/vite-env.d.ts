/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Backend origin, e.g. https://resume-tailor-api.onrender.com
   * Leave unset in development so requests stay relative and Vite proxies them.
   */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
