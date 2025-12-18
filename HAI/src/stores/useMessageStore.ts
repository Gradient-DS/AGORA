/**
 * Message store for AG-UI Protocol messages.
 */

import { create } from 'zustand';
import type { ChatMessage } from '@/types';

type ProcessingStatus = 'thinking' | 'routing' | 'executing_tools' | null;

interface MessageStore {
  messages: ChatMessage[];
  processingStatus: ProcessingStatus;
  isTyping: boolean;
  addMessage: (message: Omit<ChatMessage, 'timestamp'>) => void;
  updateMessageContent: (messageId: string, content: string, append: boolean) => void;
  finalizeMessage: (messageId: string) => void;
  setProcessingStatus: (status: ProcessingStatus) => void;
  setTyping: (isTyping: boolean) => void;
  clearMessages: () => void;
  replaceMessages: (messages: ChatMessage[]) => void;
}

export const useMessageStore = create<MessageStore>((set) => ({
  messages: [],
  processingStatus: null,
  isTyping: false,

  addMessage: (message) => {
    const newMessage: ChatMessage = {
      ...message,
      timestamp: new Date(),
    };
    set((state) => {
      const existingIndex = state.messages.findIndex((msg) => msg.id === message.id);
      if (existingIndex !== -1) {
        const updatedMessages = [...state.messages];
        updatedMessages[existingIndex] = {
          ...updatedMessages[existingIndex],
          ...newMessage,
        };
        return { messages: updatedMessages };
      }
      return {
        messages: [...state.messages, newMessage],
      };
    });
  },

  updateMessageContent: (messageId, content, append) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId
          ? { ...msg, content: append ? msg.content + content : content }
          : msg
      ),
    }));
  },

  finalizeMessage: (messageId) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId ? { ...msg, isStreaming: false } : msg
      ),
    }));
  },

  setProcessingStatus: (status) => {
    console.log('[MessageStore] Processing status:', status);
    set({ processingStatus: status });
  },

  setTyping: (isTyping) => {
    set({ isTyping });
  },

  clearMessages: () => {
    set({ messages: [], processingStatus: null, isTyping: false });
  },

  replaceMessages: (messages: ChatMessage[]) => {
    set({ messages, processingStatus: null, isTyping: false });
  },
}));
