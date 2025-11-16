import { create } from 'zustand';
import type { ToolApprovalRequest } from '@/types/schemas';

interface ApprovalStore {
  pendingApprovals: ToolApprovalRequest[];
  currentApproval: ToolApprovalRequest | null;
  addApproval: (approval: ToolApprovalRequest) => void;
  removeApproval: (approvalId: string) => void;
  setCurrentApproval: (approval: ToolApprovalRequest | null) => void;
  clearApprovals: () => void;
}

export const useApprovalStore = create<ApprovalStore>((set) => ({
  pendingApprovals: [],
  currentApproval: null,

  addApproval: (approval) => {
    set((state) => ({
      pendingApprovals: [...state.pendingApprovals, approval],
      currentApproval: state.currentApproval ?? approval,
    }));
  },

  removeApproval: (approvalId) => {
    set((state) => {
      const filtered = state.pendingApprovals.filter((a) => a.approval_id !== approvalId);
      const isCurrent = state.currentApproval?.approval_id === approvalId;
      return {
        pendingApprovals: filtered,
        currentApproval: isCurrent ? (filtered[0] ?? null) : state.currentApproval,
      };
    });
  },

  setCurrentApproval: (approval) => {
    set({ currentApproval: approval });
  },

  clearApprovals: () => {
    set({ pendingApprovals: [], currentApproval: null });
  },
}));

