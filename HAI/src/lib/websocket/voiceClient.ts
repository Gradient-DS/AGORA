type VoiceMessageCallback = (message: VoiceMessage) => void;
type StatusCallback = (status: 'disconnected' | 'connecting' | 'connected' | 'error') => void;
type ErrorCallback = (error: Error) => void;

export interface VoiceMessage {
  type: string;
  [key: string]: unknown;
}

interface VoiceWebSocketConfig {
  url: string;
  sessionId: string;
}

export class VoiceWebSocketClient {
  private ws: WebSocket | null = null;
  private config: VoiceWebSocketConfig;
  private messageCallbacks: VoiceMessageCallback[] = [];
  private statusCallbacks: StatusCallback[] = [];
  private errorCallbacks: ErrorCallback[] = [];
  private currentStatus: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';
  private isManualClose = false;

  constructor(config: VoiceWebSocketConfig) {
    this.config = config;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      console.log('[VoiceWS] Already connected or connecting');
      return;
    }

    this.isManualClose = false;
    this.updateStatus('connecting');

    console.log(`[VoiceWS] Connecting to ${this.config.url}`);

    try {
      this.ws = new WebSocket(this.config.url);
      this.setupEventHandlers();
    } catch (error) {
      console.error('[VoiceWS] Failed to create WebSocket:', error);
      this.handleError(new Error(`Failed to create WebSocket: ${error}`));
      this.updateStatus('error');
    }
  }

  disconnect(): void {
    console.log('[VoiceWS] Manually disconnecting');
    this.isManualClose = true;

    if (this.ws) {
      this.send({ type: 'session.stop' });
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus('disconnected');
  }

  send(message: VoiceMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('[VoiceWS] Sending message:', message.type);
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('[VoiceWS] Cannot send message, not connected');
    }
  }

  startSession(instructions?: string, conversationHistory?: Array<{ role: string; content: string }>): void {
    this.send({
      type: 'session.start',
      session_id: this.config.sessionId,
      instructions,
      conversation_history: conversationHistory || [],
    });
  }

  sendAudioData(audioBase64: string): void {
    this.send({
      type: 'audio.data',
      audio: audioBase64,
    });
  }

  commitAudio(): void {
    this.send({
      type: 'audio.commit',
    });
  }

  sendTextMessage(text: string): void {
    this.send({
      type: 'text.message',
      text,
    });
  }

  cancelResponse(): void {
    this.send({
      type: 'response.cancel',
    });
  }

  onMessage(callback: VoiceMessageCallback): () => void {
    this.messageCallbacks.push(callback);
    return () => {
      this.messageCallbacks = this.messageCallbacks.filter((cb) => cb !== callback);
    };
  }

  onStatusChange(callback: StatusCallback): () => void {
    this.statusCallbacks.push(callback);
    callback(this.currentStatus);
    return () => {
      this.statusCallbacks = this.statusCallbacks.filter((cb) => cb !== callback);
    };
  }

  onError(callback: ErrorCallback): () => void {
    this.errorCallbacks.push(callback);
    return () => {
      this.errorCallbacks = this.errorCallbacks.filter((cb) => cb !== callback);
    };
  }

  getStatus(): 'disconnected' | 'connecting' | 'connected' | 'error' {
    return this.currentStatus;
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[VoiceWS] Connection established');
      this.updateStatus('connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as VoiceMessage;
        console.log('[VoiceWS] Received:', message.type);
        this.messageCallbacks.forEach((callback) => callback(message));
      } catch (error) {
        console.error('[VoiceWS] Invalid message received:', error);
        this.handleError(new Error(`Invalid message received: ${error}`));
      }
    };

    this.ws.onerror = (event) => {
      console.error('[VoiceWS] Connection error:', event);
      this.handleError(new Error('WebSocket connection error'));
    };

    this.ws.onclose = (event) => {
      console.log(`[VoiceWS] Connection closed (code: ${event.code})`);

      if (!this.isManualClose) {
        console.log('[VoiceWS] Connection closed unexpectedly');
        this.updateStatus('error');
      } else {
        this.updateStatus('disconnected');
      }
    };
  }

  private updateStatus(status: typeof this.currentStatus): void {
    this.currentStatus = status;
    this.statusCallbacks.forEach((callback) => callback(status));
  }

  private handleError(error: Error): void {
    this.errorCallbacks.forEach((callback) => callback(error));
  }
}

