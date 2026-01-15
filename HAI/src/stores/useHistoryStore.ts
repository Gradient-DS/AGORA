/**
 * History store for managing conversation history sidebar.
 */

import { create } from 'zustand';
import type { SessionMetadata } from '@/types';
import {
  fetchSessions as apiFetchSessions,
  deleteSession as apiDeleteSession,
  updateSession as apiUpdateSession,
} from '@/lib/api/sessions';

interface HistoryStore {
  sessions: SessionMetadata[];
  isLoading: boolean;
  error: string | null;
  isSidebarOpen: boolean;

  fetchSessions: (userId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, newTitle: string) => Promise<void>;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  addOrUpdateSession: (session: SessionMetadata) => void;
  clearSessions: () => void;
}

export const useHistoryStore = create<HistoryStore>((set) => ({
  sessions: [],
  isLoading: false,
  error: null,
  isSidebarOpen: false,

  fetchSessions: async (userId: string) => {
    console.log('[HistoryStore] Fetching sessions for user:', userId);
    set({ isLoading: true, error: null });

    try {
      const { sessions } = await apiFetchSessions(userId);
      console.log('[HistoryStore] Received sessions:', sessions);
      set({ sessions, isLoading: false });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to fetch sessions';
      console.error('[HistoryStore] Error fetching sessions:', message, error);
      set({ error: message, isLoading: false });
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await apiDeleteSession(sessionId);
      set((state) => ({
        sessions: state.sessions.filter((s) => s.sessionId !== sessionId),
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete session';
      console.error('[HistoryStore] Error deleting session:', message);
      set({ error: message });
    }
  },

  renameSession: async (sessionId: string, newTitle: string) => {
    try {
      const updatedSession = await apiUpdateSession(sessionId, { title: newTitle });
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.sessionId === sessionId ? updatedSession : s
        ),
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to rename session';
      console.error('[HistoryStore] Error renaming session:', message);
      set({ error: message });
      throw error; // Re-throw so UI can handle it
    }
  },

  toggleSidebar: () => {
    set((state) => ({ isSidebarOpen: !state.isSidebarOpen }));
  },

  setSidebarOpen: (open: boolean) => {
    set({ isSidebarOpen: open });
  },

  addOrUpdateSession: (session: SessionMetadata) => {
    set((state) => {
      const existingIndex = state.sessions.findIndex(
        (s) => s.sessionId === session.sessionId
      );

      if (existingIndex !== -1) {
        // Update existing session
        const updatedSessions = [...state.sessions];
        updatedSessions[existingIndex] = session;
        // Re-sort by lastActivity (most recent first)
        updatedSessions.sort(
          (a, b) => new Date(b.lastActivity).getTime() - new Date(a.lastActivity).getTime()
        );
        return { sessions: updatedSessions };
      }

      // Add new session at the beginning (most recent)
      return { sessions: [session, ...state.sessions] };
    });
  },

  clearSessions: () => {
    set({ sessions: [], error: null });
  },
}));
