/**
 * Message store for AG-UI Protocol messages.
 */

import { create } from 'zustand';
import type { ChatMessage } from '@/types';

type ProcessingStatus = 'thinking' | 'routing' | 'executing_tools' | null;

/** Buffer for spoken content that arrives before message is created */
interface SpokenBuffer {
  content: string;
  isStreaming: boolean;
}

/** localStorage key for persisted spoken content */
const SPOKEN_CONTENT_STORAGE_KEY = 'agora-spoken-content';

/** Load persisted spoken content from localStorage */
function loadPersistedSpokenContent(): Record<string, string> {
  try {
    const stored = localStorage.getItem(SPOKEN_CONTENT_STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

/** Save spoken content to localStorage */
function persistSpokenContent(messageId: string, content: string): void {
  try {
    const existing = loadPersistedSpokenContent();
    existing[messageId] = content;
    localStorage.setItem(SPOKEN_CONTENT_STORAGE_KEY, JSON.stringify(existing));
  } catch {
    // Ignore storage errors
  }
}

/** Clear persisted spoken content from localStorage */
function clearPersistedSpokenContent(): void {
  try {
    localStorage.removeItem(SPOKEN_CONTENT_STORAGE_KEY);
  } catch {
    // Ignore storage errors
  }
}

interface MessageStore {
  messages: ChatMessage[];
  processingStatus: ProcessingStatus;
  isTyping: boolean;
  /** Buffer for spoken content that arrives before message exists */
  spokenBuffers: Map<string, SpokenBuffer>;
  addMessage: (message: Omit<ChatMessage, 'timestamp'>) => void;
  updateMessageContent: (messageId: string, content: string, append: boolean) => void;
  finalizeMessage: (messageId: string) => void;
  /** Update spoken content for a message (for TTS comparison) */
  updateSpokenContent: (messageId: string, content: string, append: boolean) => void;
  /** Mark spoken content as finalized */
  finalizeSpokenMessage: (messageId: string) => void;
  /** Initialize spoken content streaming for a message */
  startSpokenContent: (messageId: string) => void;
  setProcessingStatus: (status: ProcessingStatus) => void;
  setTyping: (isTyping: boolean) => void;
  clearMessages: () => void;
  replaceMessages: (messages: ChatMessage[]) => void;
}

export const useMessageStore = create<MessageStore>((set) => ({
  messages: [],
  processingStatus: null,
  isTyping: false,
  spokenBuffers: new Map(),

  addMessage: (message) => {
    const newMessage: ChatMessage = {
      ...message,
      timestamp: new Date(),
    };
    set((state) => {
      // Check if there's buffered spoken content for this message
      const buffer = state.spokenBuffers.get(message.id);
      if (buffer) {
        newMessage.spokenContent = buffer.content;
        newMessage.isSpokenStreaming = buffer.isStreaming;
        // Remove from buffer
        const newBuffers = new Map(state.spokenBuffers);
        newBuffers.delete(message.id);

        const existingIndex = state.messages.findIndex((msg) => msg.id === message.id);
        if (existingIndex !== -1) {
          const updatedMessages = [...state.messages];
          updatedMessages[existingIndex] = {
            ...updatedMessages[existingIndex],
            ...newMessage,
          };
          return { messages: updatedMessages, spokenBuffers: newBuffers };
        }
        return {
          messages: [...state.messages, newMessage],
          spokenBuffers: newBuffers,
        };
      }

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

  startSpokenContent: (messageId) => {
    set((state) => {
      // Check if message exists
      const existingMsg = state.messages.find((msg) => msg.id === messageId);
      if (existingMsg) {
        // Don't reset if already has content (backend sends start twice)
        if (existingMsg.spokenContent) {
          return { messages: state.messages };
        }
        return {
          messages: state.messages.map((msg) =>
            msg.id === messageId
              ? { ...msg, spokenContent: '', isSpokenStreaming: true }
              : msg
          ),
        };
      }
      // Check if buffer already has content (don't reset)
      const existingBuffer = state.spokenBuffers.get(messageId);
      if (existingBuffer?.content) {
        return { spokenBuffers: state.spokenBuffers };
      }
      // Buffer it for when message is created
      const newBuffers = new Map(state.spokenBuffers);
      newBuffers.set(messageId, { content: '', isStreaming: true });
      return { spokenBuffers: newBuffers };
    });
  },

  updateSpokenContent: (messageId, content, append) => {
    set((state) => {
      // Check if message exists
      const messageExists = state.messages.some((msg) => msg.id === messageId);
      if (messageExists) {
        return {
          messages: state.messages.map((msg) =>
            msg.id === messageId
              ? { ...msg, spokenContent: append ? (msg.spokenContent || '') + content : content }
              : msg
          ),
        };
      }
      // Buffer it for when message is created
      const newBuffers = new Map(state.spokenBuffers);
      const existing = newBuffers.get(messageId) || { content: '', isStreaming: true };
      newBuffers.set(messageId, {
        ...existing,
        content: append ? existing.content + content : content,
      });
      return { spokenBuffers: newBuffers };
    });
  },

  finalizeSpokenMessage: (messageId) => {
    set((state) => {
      // Check if message exists
      const existingMsg = state.messages.find((msg) => msg.id === messageId);
      if (existingMsg) {
        // Persist spoken content to localStorage when finalized
        if (existingMsg.spokenContent) {
          persistSpokenContent(messageId, existingMsg.spokenContent);
        }
        return {
          messages: state.messages.map((msg) =>
            msg.id === messageId ? { ...msg, isSpokenStreaming: false } : msg
          ),
        };
      }
      // Update buffer and persist
      const newBuffers = new Map(state.spokenBuffers);
      const existing = newBuffers.get(messageId);
      if (existing) {
        newBuffers.set(messageId, { ...existing, isStreaming: false });
        // Persist buffered content
        if (existing.content) {
          persistSpokenContent(messageId, existing.content);
        }
      }
      return { spokenBuffers: newBuffers };
    });
  },

  setProcessingStatus: (status) => {
    console.log('[MessageStore] Processing status:', status);
    set({ processingStatus: status });
  },

  setTyping: (isTyping) => {
    set({ isTyping });
  },

  clearMessages: () => {
    clearPersistedSpokenContent();
    set({ messages: [], processingStatus: null, isTyping: false, spokenBuffers: new Map() });
  },

  replaceMessages: (messages: ChatMessage[]) => {
    // Merge persisted spoken content from localStorage
    const persistedSpoken = loadPersistedSpokenContent();
    const messagesWithSpoken = messages.map((msg) => {
      const spokenContent = persistedSpoken[msg.id];
      if (spokenContent) {
        return { ...msg, spokenContent };
      }
      return msg;
    });
    set({ messages: messagesWithSpoken, processingStatus: null, isTyping: false });
  },
}));
