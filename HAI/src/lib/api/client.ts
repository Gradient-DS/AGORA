/**
 * API client with authentication support.
 */

import { getStoredApiKey } from '@/stores/useAuthStore';

/**
 * Fetch wrapper that automatically includes the API key header.
 */
export async function apiFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const apiKey = getStoredApiKey();

  const headers = new Headers(options.headers);

  if (apiKey) {
    headers.set('X-API-Key', apiKey);
  }

  return fetch(url, {
    ...options,
    headers,
  });
}
