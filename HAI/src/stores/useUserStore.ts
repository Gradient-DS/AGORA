/**
 * User store for managing current user and available users from API.
 */

import { create } from 'zustand';
import type { UserProfile } from '@/types/user';
import { fetchUsers as apiFetchUsers } from '@/lib/api/users';

interface UserStore {
  // State
  currentUser: UserProfile | null;
  users: UserProfile[];
  isLoading: boolean;
  error: string | null;

  // Actions
  setUser: (userId: string) => void;
  clearUser: () => void;
  initializeUser: () => void;
  loadUsers: () => Promise<void>;
}

export const useUserStore = create<UserStore>((set, get) => ({
  currentUser: null,
  users: [],
  isLoading: false,
  error: null,

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
        } else {
          // Saved user no longer exists, clear it
          localStorage.removeItem('current_user');
        }
      }

      // Auto-select first user if none is saved and users exist
      if (!get().currentUser && users.length > 0) {
        console.log('[UserStore] No saved user, auto-selecting first user:', users[0].id);
        localStorage.setItem('current_user', users[0].id);
        set({ currentUser: users[0] });
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
    } else {
      console.warn('[UserStore] User not found:', userId);
    }
  },

  clearUser: () => {
    localStorage.removeItem('current_user');
    set({ currentUser: null });
  },

  initializeUser: () => {
    // Load users from API - this will also restore the saved user if exists
    get().loadUsers();
  },
}));
