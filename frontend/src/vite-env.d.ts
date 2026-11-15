/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEMO_EMAIL?: string;
  readonly VITE_DEMO_PASSWORD?: string;
  /** Absolute API origin for cross-origin deployments, e.g. https://api.example.org. Defaults to same-origin /api. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
