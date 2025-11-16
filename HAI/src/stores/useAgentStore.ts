import { create } from 'zustand';

export interface Agent {
  id: string;
  name: string;
  status: 'idle' | 'active' | 'executing_tools';
  lastActive?: Date;
}

export interface InactiveAgent {
  id: string;
  name: string;
  description: string;
  coming_soon: boolean;
}

const KNOWN_AGENTS: Record<string, string> = {
  'general-agent': 'Algemene Assistent',
  'regulation-agent': 'Regelgeving Specialist',
  'reporting-agent': 'Rapportage Specialist',
  'history-agent': 'Bedrijfsinformatie Specialist',
};

interface AgentStore {
  agents: Map<string, Agent>;
  activeAgents: Set<string>;
  inactiveAgents: InactiveAgent[];
  setAgentActive: (agentId: string) => void;
  setAgentIdle: (agentId: string) => void;
  setAgentExecutingTools: (agentId: string) => void;
  getAgent: (agentId: string) => Agent | undefined;
  getAllAgents: () => Agent[];
  getActiveAgents: () => Agent[];
  loadAgentsFromAPI: () => Promise<void>;
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
    inactiveAgents: [],

    loadAgentsFromAPI: async () => {
      try {
        const apiUrl = import.meta.env.VITE_WS_URL?.replace('ws://', 'http://').replace('wss://', 'https://').replace('/ws', '');
        const response = await fetch(`${apiUrl}/agents`);
        
        if (!response.ok) {
          console.warn('Failed to fetch agents from API, using defaults');
          return;
        }
        
        const data = await response.json();
        
        if (data.inactive_agents) {
          set({ inactiveAgents: data.inactive_agents });
          console.log(`Loaded ${data.inactive_agents.length} inactive agents from API`);
        }
      } catch (error) {
        console.warn('Failed to load agents from API:', error);
      }
    },

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

