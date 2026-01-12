/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WS_URL: string;
  readonly VITE_APP_NAME: string;
  readonly VITE_SESSION_TIMEOUT: string;
  readonly VITE_BACKEND?: 'langgraph' | 'openai' | 'mock';
  readonly VITE_ELEVENLABS_API_KEY?: string;
  readonly VITE_ELEVENLABS_VOICE_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

