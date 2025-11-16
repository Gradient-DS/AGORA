import { create } from 'zustand';

export interface Agent {
  id: string;
  name: string;
  status: 'idle' | 'active' | 'executing_tools';
  lastActive?: Date;
}

const KNOWN_AGENTS: Record<string, string> = {
  'general-agent': 'NVWA General Assistant',
  'regulation-agent': 'Regulation Analysis Expert',
  'reporting-agent': 'HAP Report Specialist',
  'history-agent': 'Company & History Specialist',
};

interface AgentStore {
  agents: Map<string, Agent>;
  activeAgents: Set<string>;
  setAgentActive: (agentId: string) => void;
  setAgentIdle: (agentId: string) => void;
  setAgentExecutingTools: (agentId: string) => void;
  getAgent: (agentId: string) => Agent | undefined;
  getAllAgents: () => Agent[];
  getActiveAgents: () => Agent[];
}

export const useAgentStore = create<AgentStore>((set, get) => {
  // Initialize with known agents
  const initialAgents = new Map<string, Agent>();
  Object.entries(KNOWN_AGENTS).forEach(([id, name]) => {
    initialAgents.set(id, {
      id,
      name,
      status: 'idle',
    });
  });

  return {
    agents: initialAgents,
    activeAgents: new Set<string>(),

    setAgentActive: (agentId: string) =>
      set((state) => {
        const agents = new Map(state.agents);
        const agent = agents.get(agentId) || {
          id: agentId,
          name: KNOWN_AGENTS[agentId] || agentId,
          status: 'active' as const,
          lastActive: new Date(),
        };
        
        agent.status = 'active';
        agent.lastActive = new Date();
        agents.set(agentId, agent);
        
        const activeAgents = new Set(state.activeAgents);
        activeAgents.add(agentId);
        
        return { agents, activeAgents };
      }),

    setAgentIdle: (agentId: string) =>
      set((state) => {
        const agents = new Map(state.agents);
        const agent = agents.get(agentId);
        if (agent) {
          agent.status = 'idle';
          agent.lastActive = new Date();
          agents.set(agentId, agent);
        }
        
        const activeAgents = new Set(state.activeAgents);
        activeAgents.delete(agentId);
        
        return { agents, activeAgents };
      }),

    setAgentExecutingTools: (agentId: string) =>
      set((state) => {
        const agents = new Map(state.agents);
        const agent = agents.get(agentId);
        if (agent) {
          agent.status = 'executing_tools';
          agent.lastActive = new Date();
          agents.set(agentId, agent);
        }
        
        return { agents };
      }),

    getAgent: (agentId: string) => get().agents.get(agentId),

    getAllAgents: () => Array.from(get().agents.values()),

    getActiveAgents: () =>
      get().getAllAgents().filter((agent) => agent.status !== 'idle'),
  };
});

