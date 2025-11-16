import { create } from 'zustand';
import { generateSessionId } from '@/lib/utils';
import type { Session } from '@/types';

interface SessionStore {
  session: Session | null;
  initializeSession: () => void;
  updateActivity: () => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  session: null,

  initializeSession: () => {
    const existingSessionId = sessionStorage.getItem('session_id');
    
    if (existingSessionId) {
      const session: Session = {
        id: existingSessionId,
        startedAt: new Date(sessionStorage.getItem('session_started') || Date.now()),
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
      sessionStorage.setItem('session_id', newSessionId);
      sessionStorage.setItem('session_started', session.startedAt.toISOString());
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
    sessionStorage.removeItem('session_id');
    sessionStorage.removeItem('session_started');
    set({ session: null });
  },
}));

