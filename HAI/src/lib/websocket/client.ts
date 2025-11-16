import { HAIMessageSchema, type HAIMessage, type UserMessage, type ToolApprovalResponse } from '@/types/schemas';

type MessageCallback = (message: HAIMessage) => void;
type StatusCallback = (status: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error') => void;
type ErrorCallback = (error: Error) => void;

interface HAIWebSocketConfig {
  url: string;
  maxReconnectAttempts?: number;
  reconnectInterval?: number;
  maxReconnectInterval?: number;
}

export class HAIWebSocketClient {
  private ws: WebSocket | null = null;
  private config: Required<HAIWebSocketConfig>;
  private messageQueue: HAIMessage[] = [];
  private reconnectAttempts = 0;
  private reconnectTimeout: number | null = null;
  private messageCallbacks: MessageCallback[] = [];
  private statusCallbacks: StatusCallback[] = [];
  private errorCallbacks: ErrorCallback[] = [];
  private currentStatus: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' = 'disconnected';
  private isManualClose = false;
  private isConnecting = false;

  constructor(config: HAIWebSocketConfig) {
    this.config = {
      url: config.url,
      maxReconnectAttempts: config.maxReconnectAttempts ?? 5,
      reconnectInterval: config.reconnectInterval ?? 3000,
      maxReconnectInterval: config.maxReconnectInterval ?? 30000,
    };
  }

  connect(): void {
    if (this.isConnecting) {
      console.log('[WebSocket] Connection attempt already in progress, skipping');
      return;
    }

    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      console.log('[WebSocket] Already connected or connecting, skipping');
      return;
    }

    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.error('[WebSocket] Max reconnect attempts reached, not attempting connection');
      this.updateStatus('error');
      return;
    }

    this.isConnecting = true;
    this.isManualClose = false;
    const status = this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
    this.updateStatus(status);
    
    console.log(`[WebSocket] ${status === 'connecting' ? 'Connecting' : `Reconnecting (attempt ${this.reconnectAttempts + 1}/${this.config.maxReconnectAttempts})`} to ${this.config.url}`);

    try {
      this.ws = new WebSocket(this.config.url);
      this.setupEventHandlers();
    } catch (error) {
      console.error('[WebSocket] Failed to create WebSocket:', error);
      this.isConnecting = false;
      this.handleError(new Error(`Failed to create WebSocket: ${error}`));
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    console.log('[WebSocket] Manually disconnecting');
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

  send(message: HAIMessage): void {
    try {
      const validated = HAIMessageSchema.parse(message);
      
      if (this.ws?.readyState === WebSocket.OPEN) {
        console.log('[WebSocket] Sending message:', message.type);
        this.ws.send(JSON.stringify(validated));
      } else {
        console.log('[WebSocket] Connection not open, queuing message:', message.type);
        this.messageQueue.push(validated);
      }
    } catch (error) {
      console.error('[WebSocket] Invalid message format:', error);
      this.handleError(new Error(`Invalid message format: ${error}`));
    }
  }

  sendUserMessage(content: string, sessionId: string, metadata?: Record<string, unknown>): void {
    const message: UserMessage = {
      type: 'user_message',
      content,
      session_id: sessionId,
      metadata: metadata ?? {},
    };
    this.send(message);
  }

  sendToolApproval(approvalId: string, approved: boolean, feedback?: string): void {
    const message: ToolApprovalResponse = {
      type: 'tool_approval_response',
      approval_id: approvalId,
      approved,
      feedback: feedback ?? null,
    };
    this.send(message);
  }

  onMessage(callback: MessageCallback): () => void {
    this.messageCallbacks.push(callback);
    return () => {
      this.messageCallbacks = this.messageCallbacks.filter(cb => cb !== callback);
    };
  }

  onStatusChange(callback: StatusCallback): () => void {
    this.statusCallbacks.push(callback);
    callback(this.currentStatus);
    return () => {
      this.statusCallbacks = this.statusCallbacks.filter(cb => cb !== callback);
    };
  }

  onError(callback: ErrorCallback): () => void {
    this.errorCallbacks.push(callback);
    return () => {
      this.errorCallbacks = this.errorCallbacks.filter(cb => cb !== callback);
    };
  }

  getStatus(): 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error' {
    return this.currentStatus;
  }

  reset(): void {
    console.log('[WebSocket] Resetting connection state');
    this.disconnect();
    this.reconnectAttempts = 0;
    this.messageQueue = [];
    this.updateStatus('disconnected');
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[WebSocket] Connection established');
      this.isConnecting = false;
      this.updateStatus('connected');
      this.reconnectAttempts = 0;
      this.flushMessageQueue();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const message = HAIMessageSchema.parse(data);
        this.messageCallbacks.forEach(callback => callback(message));
      } catch (error) {
        console.error('[WebSocket] Invalid message received:', error);
        this.handleError(new Error(`Invalid message received: ${error}`));
      }
    };

    this.ws.onerror = (event) => {
      console.error('[WebSocket] Connection error:', event);
      this.isConnecting = false;
      this.handleError(new Error('WebSocket connection error'));
    };

    this.ws.onclose = (event) => {
      console.log(`[WebSocket] Connection closed (code: ${event.code}, reason: ${event.reason || 'none'})`);
      this.isConnecting = false;
      
      if (!this.isManualClose) {
        console.log('[WebSocket] Connection closed unexpectedly, will attempt reconnect');
        this.scheduleReconnect();
      } else {
        console.log('[WebSocket] Connection closed manually');
        this.updateStatus('disconnected');
      }
    };
  }

  private flushMessageQueue(): void {
    const queueLength = this.messageQueue.length;
    if (queueLength > 0) {
      console.log(`[WebSocket] Flushing ${queueLength} queued message(s)`);
    }
    
    while (this.messageQueue.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
      const message = this.messageQueue.shift();
      if (message) {
        this.ws.send(JSON.stringify(message));
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.isManualClose) {
      console.log('[WebSocket] Manual close detected, skipping reconnect');
      return;
    }

    if (this.reconnectTimeout !== null) {
      console.log('[WebSocket] Reconnect already scheduled, skipping');
      return;
    }

    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.error(`[WebSocket] Max reconnect attempts (${this.config.maxReconnectAttempts}) reached, giving up`);
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

    console.log(`[WebSocket] Scheduling reconnect attempt ${this.reconnectAttempts}/${this.config.maxReconnectAttempts} in ${delay}ms`);

    this.reconnectTimeout = window.setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }

  private updateStatus(status: typeof this.currentStatus): void {
    this.currentStatus = status;
    this.statusCallbacks.forEach(callback => callback(status));
  }

  private handleError(error: Error): void {
    this.errorCallbacks.forEach(callback => callback(error));
  }
}

