export * from './schemas';

// UI message representation (rendered in chat)
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: Date;
  agentId?: string;
  metadata?: Record<string, unknown>;
  isStreaming?: boolean;
  toolName?: string;
  toolStatus?: 'started' | 'completed' | 'failed';
}

// Tool call UI representation
export interface ToolCallInfo {
  id: string;
  toolName: string;
  parameters?: Record<string, unknown>;
  result?: string;
  error?: string;
  status: 'started' | 'completed' | 'failed';
  parentMessageId?: string;
  agentId?: string;
  timestamp: Date;
}

// Session/Thread info
export interface Session {
  id: string;
  startedAt: Date;
  lastActivity: Date;
}

// Run state
export interface RunState {
  runId: string | null;
  threadId: string | null;
  isRunning: boolean;
  currentStep: string | null;
}

// Voice state
export interface VoiceState {
  isActive: boolean;
  isListening: boolean;
  isSpeaking: boolean;
  volume: number;
  partialTranscript: string;
}

export interface AudioVisualizerData {
  frequencies: number[];
  waveform: number[];
}

// Session metadata for history listing
export interface SessionMetadata {
  sessionId: string;
  userId: string;
  title: string;
  firstMessagePreview: string | null;
  messageCount: number;
  createdAt: string;  // ISO string from backend
  lastActivity: string;  // ISO string from backend
}
