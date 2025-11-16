import { create } from 'zustand';

export interface ToolCall {
  id: string;
  toolName: string;
  status: 'started' | 'completed' | 'failed';
  parameters?: Record<string, unknown>;
  result?: string;
  timestamp: Date;
  messageId?: string;
  agentId?: string;
}

interface ToolCallStore {
  toolCalls: ToolCall[];
  addToolCall: (toolCall: Omit<ToolCall, 'timestamp'>) => void;
  updateToolCall: (id: string, updates: Partial<ToolCall>) => void;
  clearToolCalls: () => void;
  getToolCallsByAgent: (agentId: string) => ToolCall[];
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
      console.log('[ToolCallStore] Adding new tool call:', toolCall.id, toolCall.toolName, 'for agent:', toolCall.agentId);
      return {
        toolCalls: [...state.toolCalls, { ...toolCall, timestamp: new Date() }],
      };
    }),
  
  updateToolCall: (id, updates) =>
    set((state) => {
      console.log('[ToolCallStore] Updating tool call:', id, updates);
      return {
        toolCalls: state.toolCalls.map((tc) =>
          tc.id === id ? { ...tc, ...updates } : tc
        ),
      };
    }),
  
  clearToolCalls: () => set({ toolCalls: [] }),
  
  getToolCallsByAgent: (agentId: string) =>
    get().toolCalls.filter((tc) => tc.agentId === agentId),
}));

