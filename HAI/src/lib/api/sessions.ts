/**
 * Session history API functions.
 */

import type { SessionMetadata, ChatMessage, ToolCallInfo } from '@/types';
import { env } from '@/lib/env';
import { apiFetch } from './client';

/**
 * Get the HTTP base URL from the WebSocket URL.
 * Converts ws://host:port/ws to http://host:port
 */
function getBaseUrl(): string {
  const wsUrl = env.VITE_WS_URL;
  return wsUrl
    .replace(/^ws:/, 'http:')
    .replace(/^wss:/, 'https:')
    .replace(/\/ws\/?$/, '');
}

interface SessionsResponse {
  success: boolean;
  sessions: SessionMetadata[];
  totalCount: number;
}

interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool_call' | 'tool';
  content: string;
  tool_name?: string;
  tool_call_id?: string;
  agent_id?: string;
}

interface HistoryResponse {
  success: boolean;
  session_id: string;
  history: HistoryMessage[];
  message_count: number;
}

export interface FetchHistoryResult {
  messages: ChatMessage[];
  toolCalls: ToolCallInfo[];
}

interface DeleteResponse {
  success: boolean;
  message: string;
}

/**
 * Fetch all sessions for a user.
 */
export async function fetchSessions(
  userId: string,
  limit: number = 50,
  offset: number = 0
): Promise<{ sessions: SessionMetadata[]; totalCount: number }> {
  const baseUrl = getBaseUrl();
  const params = new URLSearchParams({
    user_id: userId,
    limit: limit.toString(),
    offset: offset.toString(),
  });

  const url = `${baseUrl}/sessions?${params}`;
  const response = await apiFetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch sessions: ${response.statusText}`);
  }

  const data: SessionsResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch sessions');
  }

  return {
    sessions: data.sessions,
    totalCount: data.totalCount,
  };
}

/**
 * Fetch conversation history for a session, including tool calls.
 */
export async function fetchSessionHistory(
  sessionId: string
): Promise<FetchHistoryResult> {
  const baseUrl = getBaseUrl();

  // Request with include_tools=true to get tool call data
  const response = await apiFetch(`${baseUrl}/sessions/${sessionId}/history?include_tools=true`);

  if (!response.ok) {
    throw new Error(`Failed to fetch session history: ${response.statusText}`);
  }

  const data: HistoryResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to fetch session history');
  }

  const messages: ChatMessage[] = [];
  const toolCalls: ToolCallInfo[] = [];
  const toolResultsMap = new Map<string, string>(); // tool_call_id -> result content

  // First pass: collect tool results by their tool_call_id
  for (const msg of data.history) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      toolResultsMap.set(msg.tool_call_id, msg.content);
    }
  }

  // Second pass: build messages and tool calls
  let messageIndex = 0;
  for (const msg of data.history) {
    if (msg.role === 'user' || msg.role === 'assistant') {
      // Regular text messages
      messages.push({
        id: `history-${sessionId}-${messageIndex}`,
        role: msg.role,
        content: msg.content,
        agentId: msg.agent_id,
        timestamp: new Date(),
        isStreaming: false,
      });
      messageIndex++;
    } else if (msg.role === 'tool_call') {
      // Tool call invocation - create both a chat message (for pill) and ToolCallInfo (for debug panel)
      const toolCallId = msg.tool_call_id || `history-tc-${sessionId}-${messageIndex}`;
      const toolResult = toolResultsMap.get(toolCallId);

      // Add as chat message for the pill display
      messages.push({
        id: toolCallId,
        role: 'tool',
        content: msg.tool_name || 'unknown',
        toolName: msg.tool_name,
        toolStatus: 'completed', // Historical tool calls are always completed
        agentId: msg.agent_id,
        timestamp: new Date(),
        isStreaming: false,
      });

      // Add as ToolCallInfo for the debug panel
      let parameters: Record<string, unknown> | undefined;
      try {
        parameters = JSON.parse(msg.content);
      } catch {
        // Content might not be valid JSON, store as-is
        parameters = { raw: msg.content };
      }

      toolCalls.push({
        id: toolCallId,
        toolName: msg.tool_name || 'unknown',
        parameters,
        result: toolResult,
        status: 'completed',
        agentId: msg.agent_id,
        timestamp: new Date(),
      });

      messageIndex++;
    }
    // Skip 'tool' role messages - they are tool results, already processed above
  }

  return { messages, toolCalls };
}

/**
 * Delete a session.
 */
export async function deleteSession(sessionId: string): Promise<void> {
  const baseUrl = getBaseUrl();

  const response = await apiFetch(`${baseUrl}/sessions/${sessionId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Session not found');
    }
    throw new Error(`Failed to delete session: ${response.statusText}`);
  }

  const data: DeleteResponse = await response.json();

  if (!data.success) {
    throw new Error('Failed to delete session');
  }
}
