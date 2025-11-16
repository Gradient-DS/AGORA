export * from './schemas';

export interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  agent_id?: string;
  metadata?: Record<string, unknown>;
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

