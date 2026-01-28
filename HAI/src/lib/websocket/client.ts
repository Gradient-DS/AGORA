/**
 * AG-UI Protocol WebSocket client for AGORA HAI.
 *
 * Handles bidirectional WebSocket communication using the AG-UI Protocol.
 */

import {
  AGUIEventSchema,
  type AGUIEvent,
  type RunAgentInput,
  type CustomEvent,
  EventType,
  AGORA_TOOL_APPROVAL_RESPONSE,
} from '@/types/schemas';
import { generateUUID } from '@/lib/utils';
import { getStoredApiKey } from '@/stores/useAuthStore';
import { offlineBuffer } from './offlineBuffer';

type EventCallback = (event: AGUIEvent) => void;
type StatusCallback = (status: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error') => void;
type ErrorCallback = (error: Error) => void;

interface AGUIWebSocketConfig {
  url: string;
  maxReconnectAttempts?: number;
  reconnectInterval?: number;
  maxReconnectInterval?: number;
}

export class AGUIWebSocketClient {
  private ws: WebSocket | null = null;
  private config: Required<AGUIWebSocketConfig>;
  private messageQueue: string[] = [];
  private reconnectAttempts = 0;
  private reconnectTimeout: number | null = null;
  private eventCallbacks: EventCallback[] = [];
  private statusCallbacks: StatusCallback[] = [];
  private errorCallbacks: ErrorCallback[] = [];
  private currentStatus: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' = 'disconnected';
  private isManualClose = false;
  private isConnecting = false;

  constructor(config: AGUIWebSocketConfig) {
    this.config = {
      url: config.url,
      maxReconnectAttempts: config.maxReconnectAttempts ?? 5,
      reconnectInterval: config.reconnectInterval ?? 3000,
      maxReconnectInterval: config.maxReconnectInterval ?? 30000,
    };
  }

  connect(): void {
    if (this.isConnecting) {
      return;
    }

    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      this.updateStatus('error');
      return;
    }

    this.isConnecting = true;
    this.isManualClose = false;
    const status = this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
    this.updateStatus(status);

    try {
      let url = this.config.url;

      // Append API key as query param if available
      const apiKey = getStoredApiKey();
      if (apiKey) {
        const urlObj = new URL(url, window.location.origin);
        urlObj.searchParams.set('token', apiKey);
        url = urlObj.toString();
      }

      this.ws = new WebSocket(url);
      this.setupEventHandlers();
    } catch (error) {
      this.isConnecting = false;
      this.handleError(new Error(`Failed to create WebSocket: ${error}`));
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.isManualClose = true;
    this.isConnecting = false;
    this.reconnectAttempts = 0;

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus('disconnected');
  }

  /**
   * Send a run input to start a new agent run.
   * If offline, buffers the message in IndexedDB for later replay.
   */
  sendRunInput(threadId: string, userId: string, content: string): string {
    const runId = generateUUID();
    const input: RunAgentInput = {
      threadId,
      runId,
      userId,
      messages: [{ role: 'user', content }],
    };

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendRaw(JSON.stringify(input));
    } else {
      // Buffer for later replay
      offlineBuffer.addMessage({
        id: runId,
        content,
        timestamp: Date.now(),
        threadId,
        userId,
      }).then(() => {
        console.log('Message buffered offline');
      }).catch((error) => {
        console.error('Failed to buffer message:', error);
      });
    }

    return runId;
  }

  /**
   * Send a tool approval response.
   */
  sendToolApprovalResponse(approvalId: string, approved: boolean, feedback?: string): void {
    const event: CustomEvent = {
      type: EventType.CUSTOM,
      name: AGORA_TOOL_APPROVAL_RESPONSE,
      value: {
        approvalId,
        approved,
        feedback: feedback ?? null,
      },
    };

    this.sendRaw(JSON.stringify(event));
  }

  /**
   * Send raw JSON string over WebSocket.
   */
  private sendRaw(data: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    } else {
      this.messageQueue.push(data);
    }
  }

  /**
   * Subscribe to AG-UI events.
   */
  onEvent(callback: EventCallback): () => void {
    this.eventCallbacks.push(callback);
    return () => {
      this.eventCallbacks = this.eventCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * Subscribe to connection status changes.
   */
  onStatusChange(callback: StatusCallback): () => void {
    this.statusCallbacks.push(callback);
    callback(this.currentStatus);
    return () => {
      this.statusCallbacks = this.statusCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * Subscribe to errors.
   */
  onError(callback: ErrorCallback): () => void {
    this.errorCallbacks.push(callback);
    return () => {
      this.errorCallbacks = this.errorCallbacks.filter((cb) => cb !== callback);
    };
  }

  getStatus(): 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' {
    return this.currentStatus;
  }

  reset(): void {
    this.disconnect();
    this.reconnectAttempts = 0;
    this.messageQueue = [];
    this.updateStatus('disconnected');
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = async () => {
      this.isConnecting = false;
      this.updateStatus('connected');
      this.reconnectAttempts = 0;

      // Replay offline buffer
      try {
        const buffered = await offlineBuffer.getAndClearMessages();
        const firstMessage = buffered[0];
        if (firstMessage && this.ws?.readyState === WebSocket.OPEN) {
          // Send each buffered message as a separate message in the array
          const batchInput: RunAgentInput = {
            threadId: firstMessage.threadId,
            runId: generateUUID(),
            userId: firstMessage.userId,
            messages: buffered.map(m => ({ role: 'user' as const, content: m.content })),
          };

          this.ws.send(JSON.stringify(batchInput));
          console.log(`Replayed ${buffered.length} offline messages`);
        }
      } catch (error) {
        console.error('Failed to replay offline buffer:', error);
      }

      this.flushMessageQueue();
    };

    this.ws.onmessage = (wsEvent) => {
      try {
        const data = JSON.parse(wsEvent.data);
        const parseResult = AGUIEventSchema.safeParse(data);

        if (parseResult.success) {
          this.eventCallbacks.forEach((callback) => callback(parseResult.data));
        } else {
          // Still try to handle it as a raw event
          this.eventCallbacks.forEach((callback) =>
            callback({ type: EventType.RAW, data } as AGUIEvent)
          );
        }
      } catch (error) {
        this.handleError(new Error(`Error parsing message: ${error}`));
      }
    };

    this.ws.onerror = () => {
      this.isConnecting = false;
      this.handleError(new Error('WebSocket connection error'));
    };

    this.ws.onclose = (event) => {
      this.isConnecting = false;

      // Detect auth failure (code 4001 from gateway)
      if (event.code === 4001) {
        this.updateStatus('error');
        this.handleError(new Error('AUTH_REQUIRED'));
        return; // Don't attempt reconnect for auth errors
      }

      if (!this.isManualClose) {
        this.scheduleReconnect();
      } else {
        this.updateStatus('disconnected');
      }
    };
  }

  private flushMessageQueue(): void {
    while (this.messageQueue.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
      const message = this.messageQueue.shift();
      if (message) {
        this.ws.send(message);
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.isManualClose) {
      return;
    }

    if (this.reconnectTimeout !== null) {
      return;
    }

    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      this.updateStatus('error');
      this.handleError(new Error(`Failed to connect after ${this.config.maxReconnectAttempts} attempts`));
      return;
    }

    const delay = Math.min(
      this.config.reconnectInterval * Math.pow(2, this.reconnectAttempts),
      this.config.maxReconnectInterval
    );

    this.reconnectAttempts++;
    this.updateStatus('reconnecting');

    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }

  private updateStatus(status: typeof this.currentStatus): void {
    this.currentStatus = status;
    this.statusCallbacks.forEach((callback) => callback(status));
  }

  private handleError(error: Error): void {
    this.errorCallbacks.forEach((callback) => callback(error));
  }
}
