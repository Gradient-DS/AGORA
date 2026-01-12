import { z } from 'zod';

// Runtime config injected at container startup (see docker-entrypoint.sh)
declare global {
  interface Window {
    __RUNTIME_CONFIG__?: {
      ELEVENLABS_API_KEY?: string;
      ELEVENLABS_VOICE_ID?: string;
    };
  }
}

const envSchema = z.object({
  VITE_WS_URL: z.string().url(),
  VITE_APP_NAME: z.string().default('AGORA HAI'),
  VITE_SESSION_TIMEOUT: z.string().transform(Number).default('3600000'),
  VITE_ELEVENLABS_API_KEY: z.string().optional().default(''),
  VITE_ELEVENLABS_VOICE_ID: z.string().optional().default('pNInz6obpgDQGcFmaJgB'),
  VITE_BACKEND: z
    .enum(['langgraph', 'openai', 'mock'])
    .optional()
    .default('langgraph'),
});

function validateEnv() {
  try {
    return envSchema.parse(import.meta.env);
  } catch (error) {
    console.error('Invalid environment configuration:', error);
    throw new Error('Failed to load environment configuration');
  }
}

export const env = validateEnv();

export function getEnvVariable(key: keyof typeof env): string {
  return env[key] as string;
}

/**
 * Get the WebSocket URL for the selected backend.
 * If VITE_BACKEND is set to a non-default value, uses path-based routing: /api/{backend}/ws
 * Otherwise uses the default /ws endpoint.
 */
export function getWebSocketUrl(): string {
  const baseUrl = env.VITE_WS_URL.replace(/\/ws\/?$/, '');
  const backend = env.VITE_BACKEND;

  if (backend && backend !== 'langgraph') {
    // Use explicit backend path for non-default backends
    return `${baseUrl}/api/${backend}/ws`;
  }

  // Use default /ws endpoint (gateway will route to default backend)
  return env.VITE_WS_URL;
}

/**
 * Get the HTTP API base URL for the selected backend.
 */
export function getApiBaseUrl(): string {
  const wsUrl = getWebSocketUrl();
  return wsUrl
    .replace(/^ws:/, 'http:')
    .replace(/^wss:/, 'https:')
    .replace(/\/ws\/?$/, '');
}

/**
 * Get ElevenLabs API key.
 * Checks runtime config first (Docker), then falls back to build-time env.
 */
export function getElevenLabsApiKey(): string {
  return window.__RUNTIME_CONFIG__?.ELEVENLABS_API_KEY || env.VITE_ELEVENLABS_API_KEY || '';
}

/**
 * Get ElevenLabs voice ID.
 * Checks runtime config first (Docker), then falls back to build-time env.
 */
export function getElevenLabsVoiceId(): string {
  return window.__RUNTIME_CONFIG__?.ELEVENLABS_VOICE_ID || env.VITE_ELEVENLABS_VOICE_ID || 'pNInz6obpgDQGcFmaJgB';
}

