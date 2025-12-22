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
      console.log('[AG-UI WebSocket] Connection attempt already in progress, skipping');
      return;
    }

    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      console.log('[AG-UI WebSocket] Already connected or connecting, skipping');
      return;
    }

    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.error('[AG-UI WebSocket] Max reconnect attempts reached, not attempting connection');
      this.updateStatus('error');
      return;
    }

    this.isConnecting = true;
    this.isManualClose = false;
    const status = this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
    this.updateStatus(status);

    console.log(
      `[AG-UI WebSocket] ${status === 'connecting' ? 'Connecting' : `Reconnecting (attempt ${this.reconnectAttempts + 1}/${this.config.maxReconnectAttempts})`} to ${this.config.url}`
    );

    try {
      this.ws = new WebSocket(this.config.url);
      this.setupEventHandlers();
    } catch (error) {
      console.error('[AG-UI WebSocket] Failed to create WebSocket:', error);
      this.isConnecting = false;
      this.handleError(new Error(`Failed to create WebSocket: ${error}`));
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    console.log('[AG-UI WebSocket] Manually disconnecting');
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
   */
  sendRunInput(threadId: string, userId: string, content: string, context?: Record<string, unknown>): string {
    const runId = generateUUID();
    const input: RunAgentInput = {
      threadId,
      runId,
      userId,
      messages: [{ role: 'user', content }],
      context,
    };

    this.sendRaw(JSON.stringify(input));
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
      console.log('[AG-UI WebSocket] Sending message');
      this.ws.send(data);
    } else {
      console.log('[AG-UI WebSocket] Connection not open, queuing message');
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
    console.log('[AG-UI WebSocket] Resetting connection state');
    this.disconnect();
    this.reconnectAttempts = 0;
    this.messageQueue = [];
    this.updateStatus('disconnected');
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[AG-UI WebSocket] Connection established');
      this.isConnecting = false;
      this.updateStatus('connected');
      this.reconnectAttempts = 0;
      this.flushMessageQueue();
    };

    this.ws.onmessage = (wsEvent) => {
      try {
        const data = JSON.parse(wsEvent.data);
        const parseResult = AGUIEventSchema.safeParse(data);

        if (parseResult.success) {
          this.eventCallbacks.forEach((callback) => callback(parseResult.data));
        } else {
          console.warn('[AG-UI WebSocket] Invalid event received:', parseResult.error);
          // Still try to handle it as a raw event
          this.eventCallbacks.forEach((callback) =>
            callback({ type: EventType.RAW, data } as AGUIEvent)
          );
        }
      } catch (error) {
        console.error('[AG-UI WebSocket] Error parsing message:', error);
        this.handleError(new Error(`Error parsing message: ${error}`));
      }
    };

    this.ws.onerror = (wsEvent) => {
      console.error('[AG-UI WebSocket] Connection error:', wsEvent);
      this.isConnecting = false;
      this.handleError(new Error('WebSocket connection error'));
    };

    this.ws.onclose = (wsEvent) => {
      console.log(
        `[AG-UI WebSocket] Connection closed (code: ${wsEvent.code}, reason: ${wsEvent.reason || 'none'})`
      );
      this.isConnecting = false;

      if (!this.isManualClose) {
        console.log('[AG-UI WebSocket] Connection closed unexpectedly, will attempt reconnect');
        this.scheduleReconnect();
      } else {
        console.log('[AG-UI WebSocket] Connection closed manually');
        this.updateStatus('disconnected');
      }
    };
  }

  private flushMessageQueue(): void {
    const queueLength = this.messageQueue.length;
    if (queueLength > 0) {
      console.log(`[AG-UI WebSocket] Flushing ${queueLength} queued message(s)`);
    }

    while (this.messageQueue.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
      const message = this.messageQueue.shift();
      if (message) {
        this.ws.send(message);
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.isManualClose) {
      console.log('[AG-UI WebSocket] Manual close detected, skipping reconnect');
      return;
    }

    if (this.reconnectTimeout !== null) {
      console.log('[AG-UI WebSocket] Reconnect already scheduled, skipping');
      return;
    }

    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.error(
        `[AG-UI WebSocket] Max reconnect attempts (${this.config.maxReconnectAttempts}) reached, giving up`
      );
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

    console.log(
      `[AG-UI WebSocket] Scheduling reconnect attempt ${this.reconnectAttempts}/${this.config.maxReconnectAttempts} in ${delay}ms`
    );

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
