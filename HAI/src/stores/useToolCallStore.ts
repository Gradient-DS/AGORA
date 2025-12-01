/**
 * Tool call store for AG-UI Protocol tool events.
 */

import { create } from 'zustand';
import type { ToolCallInfo } from '@/types';

interface ToolCallStore {
  toolCalls: ToolCallInfo[];
  addToolCall: (toolCall: Omit<ToolCallInfo, 'timestamp'>) => void;
  updateToolCall: (id: string, updates: Partial<ToolCallInfo>) => void;
  clearToolCalls: () => void;
  getToolCallsByMessage: (messageId: string) => ToolCallInfo[];
  getToolCallsByAgent: (agentId: string) => ToolCallInfo[];
}

export const useToolCallStore = create<ToolCallStore>((set, get) => ({
  toolCalls: [],

  addToolCall: (toolCall) =>
    set((state) => {
      const exists = state.toolCalls.some((tc) => tc.id === toolCall.id);
      if (exists) {
        console.log('[ToolCallStore] Tool call already exists:', toolCall.id);
        return state;
      }
      console.log('[ToolCallStore] Adding tool call:', toolCall.id, toolCall.toolName);
      return {
        toolCalls: [...state.toolCalls, { ...toolCall, timestamp: new Date() }],
      };
    }),

  updateToolCall: (id, updates) =>
    set((state) => {
      console.log('[ToolCallStore] Updating tool call:', id, updates);
      return {
        toolCalls: state.toolCalls.map((tc) => (tc.id === id ? { ...tc, ...updates } : tc)),
      };
    }),

  clearToolCalls: () => set({ toolCalls: [] }),

  getToolCallsByMessage: (messageId: string) =>
    get().toolCalls.filter((tc) => tc.parentMessageId === messageId),

  getToolCallsByAgent: (agentId: string) =>
    get().toolCalls.filter((tc) => tc.agentId === agentId),
}));
