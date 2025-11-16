import { create } from 'zustand';
import { generateMessageId } from '@/lib/utils';
import type { Message } from '@/types';
import type { ProcessingStatus } from '@/types/schemas';

interface MessageStore {
  messages: Message[];
  currentStatus: ProcessingStatus | null;
  isTyping: boolean;
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void;
  updateStatus: (status: ProcessingStatus | null) => void;
  setTyping: (isTyping: boolean) => void;
  clearMessages: () => void;
}

export const useMessageStore = create<MessageStore>((set) => ({
  messages: [],
  currentStatus: null,
  isTyping: false,

  addMessage: (message) => {
    const newMessage: Message = {
      ...message,
      id: generateMessageId(),
      timestamp: new Date(),
    };
    set((state) => ({
      messages: [...state.messages, newMessage],
    }));
  },

  updateStatus: (status) => {
    set({ currentStatus: status });
  },

  setTyping: (isTyping) => {
    set({ isTyping });
  },

  clearMessages: () => {
    set({ messages: [], currentStatus: null, isTyping: false });
  },
}));

