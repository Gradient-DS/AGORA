import { z } from 'zod';

const envSchema = z.object({
  VITE_WS_URL: z.string().url(),
  VITE_OPENAI_API_KEY: z.string().min(1),
  VITE_APP_NAME: z.string().default('AGORA HAI'),
  VITE_SESSION_TIMEOUT: z.string().transform(Number).default('3600000'),
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

