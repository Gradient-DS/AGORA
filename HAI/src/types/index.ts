export * from './schemas';

export interface Message {
  id: string;
  type: 'user' | 'assistant' | 'tool_call';
  content: string;
  timestamp: Date;
  agent_id?: string;
  metadata?: Record<string, unknown>;
  isStreaming?: boolean;
  tool_name?: string;
  tool_status?: 'started' | 'completed' | 'failed';
}

export interface Session {
  id: string;
  startedAt: Date;
  lastActivity: Date;
}

export interface VoiceState {
  isActive: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  volume: number;
}

export interface AudioVisualizerData {
  frequencies: number[];
  waveform: number[];
}

