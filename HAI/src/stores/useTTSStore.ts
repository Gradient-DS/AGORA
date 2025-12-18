/**
 * TTS (Text-to-Speech) store for AGORA HAI.
 *
 * Manages ElevenLabs TTS state including user toggle and playback status.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface TTSState {
  /** Whether TTS is enabled by the user */
  isEnabled: boolean;
  /** Whether audio is currently playing */
  isSpeaking: boolean;
  /** Toggle TTS on/off */
  toggleEnabled: () => void;
  /** Set enabled state directly */
  setEnabled: (enabled: boolean) => void;
  /** Set speaking state */
  setIsSpeaking: (speaking: boolean) => void;
}

export const useTTSStore = create<TTSState>()(
  persist(
    (set) => ({
      isEnabled: false,
      isSpeaking: false,
      toggleEnabled: () => set((state) => ({ isEnabled: !state.isEnabled })),
      setEnabled: (enabled) => set({ isEnabled: enabled }),
      setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),
    }),
    {
      name: 'agora-tts-settings',
      partialize: (state) => ({ isEnabled: state.isEnabled }),
    }
  )
);
