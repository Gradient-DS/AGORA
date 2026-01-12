import { create } from 'zustand';
import type { VoiceState } from '@/types';

interface VoiceStore extends VoiceState {
  setActive: (isActive: boolean) => void;
  setListening: (isListening: boolean) => void;
  setSpeaking: (isSpeaking: boolean) => void;
  setVolume: (volume: number) => void;
  setPartialTranscript: (transcript: string) => void;
  reset: () => void;
}

const initialState: VoiceState = {
  isActive: false,
  isListening: false,
  isSpeaking: false,
  volume: 0,
  partialTranscript: '',
};

export const useVoiceStore = create<VoiceStore>((set) => ({
  ...initialState,

  setActive: (isActive) => {
    set({ isActive });
  },

  setListening: (isListening) => {
    set({ isListening });
  },

  setSpeaking: (isSpeaking) => {
    set({ isSpeaking });
  },

  setVolume: (volume) => {
    set({ volume });
  },

  setPartialTranscript: (partialTranscript) => {
    set({ partialTranscript });
  },

  reset: () => {
    set(initialState);
  },
}));

