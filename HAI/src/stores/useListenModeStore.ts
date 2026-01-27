import { create } from 'zustand';

interface ListenModeStore {
  bufferedCount: number;
  setBufferedCount: (count: number) => void;
  incrementBufferedCount: () => void;
  resetBufferedCount: () => void;
}

export const useListenModeStore = create<ListenModeStore>((set) => ({
  bufferedCount: 0,
  setBufferedCount: (count) => set({ bufferedCount: count }),
  incrementBufferedCount: () => set((s) => ({ bufferedCount: s.bufferedCount + 1 })),
  resetBufferedCount: () => set({ bufferedCount: 0 }),
}));
