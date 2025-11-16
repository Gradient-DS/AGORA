import { create } from 'zustand';
import type { Message } from '@/types';
import type { ProcessingStatus } from '@/types/schemas';

interface MessageStore {
  messages: Message[];
  currentStatus: ProcessingStatus | null;
  isTyping: boolean;
  addMessage: (message: Omit<Message, 'timestamp'>) => void;
  updateMessageContent: (messageId: string, content: string, append: boolean) => void;
  finalizeMessage: (messageId: string) => void;
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
      timestamp: new Date(),
    };
    set((state) => {
      // Check if message already exists (for tool_call updates)
      const existingIndex = state.messages.findIndex((msg) => msg.id === message.id);
      if (existingIndex !== -1) {
        // Update existing message
        const updatedMessages = [...state.messages];
        updatedMessages[existingIndex] = {
          ...updatedMessages[existingIndex],
          ...newMessage,
        };
        return { messages: updatedMessages };
      }
      // Add new message
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

