/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WS_URL: string;
  readonly VITE_OPENAI_API_KEY: string;
  readonly VITE_APP_NAME: string;
  readonly VITE_SESSION_TIMEOUT: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

