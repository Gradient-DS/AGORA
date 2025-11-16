import { create } from 'zustand';
import type { ConnectionStatus } from '@/types/schemas';

interface ConnectionStore {
  status: ConnectionStatus;
  error: Error | null;
  reconnectAttempts: number;
  setStatus: (status: ConnectionStatus) => void;
  setError: (error: Error | null) => void;
  incrementReconnectAttempts: () => void;
  resetReconnectAttempts: () => void;
}

export const useConnectionStore = create<ConnectionStore>((set) => ({
  status: 'disconnected',
  error: null,
  reconnectAttempts: 0,

  setStatus: (status) => {
    set({ status });
  },

  setError: (error) => {
    set({ error });
  },

  incrementReconnectAttempts: () => {
    set((state) => ({ reconnectAttempts: state.reconnectAttempts + 1 }));
  },

  resetReconnectAttempts: () => {
    set({ reconnectAttempts: 0 });
  },
}));

