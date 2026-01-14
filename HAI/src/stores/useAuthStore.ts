import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthStore {
  apiKey: string | null;
  isAuthRequired: boolean | null; // null = unknown, true/false = determined
  authError: string | null;

  setApiKey: (key: string | null) => void;
  setAuthRequired: (required: boolean) => void;
  setAuthError: (error: string | null) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      apiKey: null,
      isAuthRequired: null,
      authError: null,

      setApiKey: (apiKey) => set({ apiKey, authError: null }),
      setAuthRequired: (isAuthRequired) => set({ isAuthRequired }),
      setAuthError: (authError) => set({ authError }),
      clearAuth: () => set({ apiKey: null, authError: null }),
    }),
    {
      name: 'agora-auth',
      partialize: (state) => ({ apiKey: state.apiKey }), // Only persist API key
    }
  )
);

// Helper for other modules to get the stored API key
export function getStoredApiKey(): string | null {
  return useAuthStore.getState().apiKey;
}
