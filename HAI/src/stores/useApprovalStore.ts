/**
 * Approval store for AG-UI Protocol human-in-the-loop approval flow.
 */

import { create } from 'zustand';
import type { RiskLevel } from '@/types/schemas';

export interface ApprovalRequest {
  approvalId: string;
  toolName: string;
  toolDescription: string;
  parameters: Record<string, unknown>;
  reasoning: string;
  riskLevel: RiskLevel;
}

interface ApprovalStore {
  pendingApprovals: ApprovalRequest[];
  currentApproval: ApprovalRequest | null;
  addApproval: (approval: ApprovalRequest) => void;
  removeApproval: (approvalId: string) => void;
  setCurrentApproval: (approval: ApprovalRequest | null) => void;
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
      const filtered = state.pendingApprovals.filter((a) => a.approvalId !== approvalId);
      const isCurrent = state.currentApproval?.approvalId === approvalId;
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
