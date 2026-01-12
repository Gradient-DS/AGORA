/**
 * User store for managing current user and available users from API.
 */

import { create } from 'zustand';
import type { UserProfile, UserPreferences } from '@/types/user';
import { fetchUsers as apiFetchUsers, fetchUserPreferences } from '@/lib/api/users';

interface UserStore {
  // State
  currentUser: UserProfile | null;
  users: UserProfile[];
  preferences: UserPreferences | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  setUser: (userId: string) => void;
  clearUser: () => void;
  initializeUser: () => void;
  loadUsers: () => Promise<void>;
  loadPreferences: (userId: string) => Promise<void>;
}

export const useUserStore = create<UserStore>((set, get) => ({
  currentUser: null,
  users: [],
  preferences: null,
  isLoading: false,
  error: null,

  loadPreferences: async (userId: string) => {
    try {
      const preferences = await fetchUserPreferences(userId);
      set({ preferences });
    } catch (error) {
      console.error('[UserStore] Error loading preferences:', error);
      // Default preferences on error
      set({ preferences: { spoken_text_type: 'summarize' } });
    }
  },

  loadUsers: async () => {
    console.log('[UserStore] Loading users from API');
    set({ isLoading: true, error: null });

    try {
      const { users } = await apiFetchUsers();
      console.log('[UserStore] Loaded users:', users.length);
      set({ users, isLoading: false });

      // If we have a saved user ID, try to restore it
      const savedUserId = localStorage.getItem('current_user');
      if (savedUserId) {
        const savedUser = users.find((u) => u.id === savedUserId);
        if (savedUser) {
          set({ currentUser: savedUser });
          // Load preferences for the restored user
          get().loadPreferences(savedUser.id);
        } else {
          // Saved user no longer exists, clear it
          localStorage.removeItem('current_user');
        }
      }

      // Auto-select first user if none is saved and users exist
      const firstUser = users[0];
      if (!get().currentUser && firstUser) {
        console.log('[UserStore] No saved user, auto-selecting first user:', firstUser.id);
        localStorage.setItem('current_user', firstUser.id);
        set({ currentUser: firstUser });
        // Load preferences for the auto-selected user
        get().loadPreferences(firstUser.id);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load users';
      console.error('[UserStore] Error loading users:', message);
      set({ error: message, isLoading: false });
    }
  },

  setUser: (userId: string) => {
    const { users } = get();
    const user = users.find((u) => u.id === userId);
    if (user) {
      localStorage.setItem('current_user', userId);
      set({ currentUser: user });
      // Load preferences for the new user
      get().loadPreferences(userId);
    } else {
      console.warn('[UserStore] User not found:', userId);
    }
  },

  clearUser: () => {
    localStorage.removeItem('current_user');
    set({ currentUser: null, preferences: null });
  },

  initializeUser: () => {
    // Load users from API - this will also restore the saved user if exists
    get().loadUsers();
  },
}));
