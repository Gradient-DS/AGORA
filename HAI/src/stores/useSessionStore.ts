import { create } from 'zustand';
import { generateSessionId } from '@/lib/utils';
import type { Session } from '@/types';

interface SessionStore {
  session: Session | null;
  initializeSession: () => void;
  updateActivity: () => void;
  clearSession: () => void;
  switchToSession: (sessionId: string) => void;
  startNewSession: () => void;
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  session: null,

  initializeSession: () => {
    const existingSessionId = localStorage.getItem('session_id');

    if (existingSessionId) {
      const session: Session = {
        id: existingSessionId,
        startedAt: new Date(localStorage.getItem('session_started') || Date.now()),
        lastActivity: new Date(),
      };
      set({ session });
    } else {
      const newSessionId = generateSessionId();
      const session: Session = {
        id: newSessionId,
        startedAt: new Date(),
        lastActivity: new Date(),
      };
      localStorage.setItem('session_id', newSessionId);
      localStorage.setItem('session_started', session.startedAt.toISOString());
      set({ session });
    }
  },

  updateActivity: () => {
    const { session } = get();
    if (session) {
      set({ session: { ...session, lastActivity: new Date() } });
    }
  },

  clearSession: () => {
    localStorage.removeItem('session_id');
    localStorage.removeItem('session_started');
    set({ session: null });
  },

  switchToSession: (sessionId: string) => {
    const session: Session = {
      id: sessionId,
      startedAt: new Date(), // Will be overridden by actual history if needed
      lastActivity: new Date(),
    };
    localStorage.setItem('session_id', sessionId);
    localStorage.setItem('session_started', session.startedAt.toISOString());
    set({ session });
  },

  startNewSession: () => {
    const newSessionId = generateSessionId();
    const session: Session = {
      id: newSessionId,
      startedAt: new Date(),
      lastActivity: new Date(),
    };
    localStorage.setItem('session_id', newSessionId);
    localStorage.setItem('session_started', session.startedAt.toISOString());
    set({ session });
  },
}));

