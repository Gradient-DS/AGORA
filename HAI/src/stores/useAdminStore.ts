/**
 * Admin store for user management.
 */

import { create } from 'zustand';
import type { UserProfile, CreateUserRequest, UpdateUserRequest } from '@/types/user';
import {
  fetchUsers as apiFetchUsers,
  createUser as apiCreateUser,
  updateUser as apiUpdateUser,
  deleteUser as apiDeleteUser,
} from '@/lib/api/users';

interface AdminState {
  // State
  users: UserProfile[];
  selectedUser: UserProfile | null;
  isLoading: boolean;
  error: string | null;
  totalCount: number;
  isAdminPanelOpen: boolean;

  // Modal states
  isCreateModalOpen: boolean;
  isEditModalOpen: boolean;
  isDeleteModalOpen: boolean;
  userToDelete: UserProfile | null;

  // Actions
  loadUsers: () => Promise<void>;
  selectUser: (user: UserProfile | null) => void;
  createUser: (data: CreateUserRequest) => Promise<UserProfile>;
  updateUser: (userId: string, data: UpdateUserRequest) => Promise<UserProfile>;
  deleteUser: (userId: string) => Promise<void>;
  clearError: () => void;

  // Panel actions
  openAdminPanel: () => void;
  closeAdminPanel: () => void;
  toggleAdminPanel: () => void;

  // Modal actions
  openCreateModal: () => void;
  closeCreateModal: () => void;
  openEditModal: (user: UserProfile) => void;
  closeEditModal: () => void;
  openDeleteModal: (user: UserProfile) => void;
  closeDeleteModal: () => void;
}

export const useAdminStore = create<AdminState>((set, get) => ({
  // Initial state
  users: [],
  selectedUser: null,
  isLoading: false,
  error: null,
  totalCount: 0,
  isAdminPanelOpen: false,

  // Modal states
  isCreateModalOpen: false,
  isEditModalOpen: false,
  isDeleteModalOpen: false,
  userToDelete: null,

  // Actions
  loadUsers: async () => {
    console.log('[AdminStore] Loading users');
    set({ isLoading: true, error: null });

    try {
      const { users, totalCount } = await apiFetchUsers();
      console.log('[AdminStore] Loaded users:', users.length);
      set({ users, totalCount, isLoading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load users';
      console.error('[AdminStore] Error loading users:', message);
      set({ error: message, isLoading: false });
    }
  },

  selectUser: (user: UserProfile | null) => {
    set({ selectedUser: user });
  },

  createUser: async (data: CreateUserRequest) => {
    console.log('[AdminStore] Creating user:', data.email);
    set({ isLoading: true, error: null });

    try {
      const newUser = await apiCreateUser(data);
      console.log('[AdminStore] Created user:', newUser.id);

      set((state) => ({
        users: [newUser, ...state.users],
        totalCount: state.totalCount + 1,
        isLoading: false,
        isCreateModalOpen: false,
      }));

      return newUser;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create user';
      console.error('[AdminStore] Error creating user:', message);
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  updateUser: async (userId: string, data: UpdateUserRequest) => {
    console.log('[AdminStore] Updating user:', userId);
    set({ isLoading: true, error: null });

    try {
      const updatedUser = await apiUpdateUser(userId, data);
      console.log('[AdminStore] Updated user:', updatedUser.id);

      set((state) => ({
        users: state.users.map((u) => (u.id === userId ? updatedUser : u)),
        selectedUser: state.selectedUser?.id === userId ? updatedUser : state.selectedUser,
        isLoading: false,
        isEditModalOpen: false,
      }));

      return updatedUser;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to update user';
      console.error('[AdminStore] Error updating user:', message);
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  deleteUser: async (userId: string) => {
    console.log('[AdminStore] Deleting user:', userId);
    set({ isLoading: true, error: null });

    try {
      await apiDeleteUser(userId);
      console.log('[AdminStore] Deleted user:', userId);

      set((state) => ({
        users: state.users.filter((u) => u.id !== userId),
        selectedUser: state.selectedUser?.id === userId ? null : state.selectedUser,
        totalCount: state.totalCount - 1,
        isLoading: false,
        isDeleteModalOpen: false,
        userToDelete: null,
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete user';
      console.error('[AdminStore] Error deleting user:', message);
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  clearError: () => {
    set({ error: null });
  },

  // Panel actions
  openAdminPanel: () => {
    set({ isAdminPanelOpen: true });
    // Load users when opening panel
    get().loadUsers();
  },

  closeAdminPanel: () => {
    set({ isAdminPanelOpen: false, selectedUser: null });
  },

  toggleAdminPanel: () => {
    const isOpen = get().isAdminPanelOpen;
    if (!isOpen) {
      get().openAdminPanel();
    } else {
      get().closeAdminPanel();
    }
  },

  // Modal actions
  openCreateModal: () => {
    set({ isCreateModalOpen: true, error: null });
  },

  closeCreateModal: () => {
    set({ isCreateModalOpen: false });
  },

  openEditModal: (user: UserProfile) => {
    set({ isEditModalOpen: true, selectedUser: user, error: null });
  },

  closeEditModal: () => {
    set({ isEditModalOpen: false });
  },

  openDeleteModal: (user: UserProfile) => {
    set({ isDeleteModalOpen: true, userToDelete: user, error: null });
  },

  closeDeleteModal: () => {
    set({ isDeleteModalOpen: false, userToDelete: null });
  },
}));
