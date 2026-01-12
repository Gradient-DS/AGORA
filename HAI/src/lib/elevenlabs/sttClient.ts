/**
 * ElevenLabs STT client for AGORA HAI.
 *
 * Real-time speech-to-text using ElevenLabs WebSocket API.
 * Follows the same patterns as the TTS client.
 *
 * API Reference: https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
 */

import { env } from '@/lib/env';

interface ElevenLabsSTTConfig {
  apiKey: string;
  sampleRate?: number;
  languageCode?: string;
}

// Supported audio formats for ElevenLabs STT
type AudioFormat = 'pcm_8000' | 'pcm_16000' | 'pcm_22050' | 'pcm_24000' | 'pcm_44100';

function sampleRateToAudioFormat(sampleRate: number): AudioFormat {
  // Map sample rate to closest supported ElevenLabs format
  if (sampleRate <= 8000) return 'pcm_8000';
  if (sampleRate <= 16000) return 'pcm_16000';
  if (sampleRate <= 22050) return 'pcm_22050';
  if (sampleRate <= 24000) return 'pcm_24000';
  return 'pcm_44100'; // 44100 or 48000 -> pcm_44100
}

type TranscriptCallback = (text: string, isFinal: boolean) => void;
type StatusCallback = (status: 'disconnected' | 'connecting' | 'connected' | 'error') => void;
type ErrorCallback = (error: Error) => void;

class ElevenLabsSTTClient {
  private config: ElevenLabsSTTConfig;
  private ws: WebSocket | null = null;
  private transcriptCallbacks: TranscriptCallback[] = [];
  private statusCallbacks: StatusCallback[] = [];
  private errorCallbacks: ErrorCallback[] = [];
  private currentStatus: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';

  constructor(config: Partial<ElevenLabsSTTConfig> = {}) {
    this.config = {
      apiKey: config.apiKey || env.VITE_ELEVENLABS_API_KEY || '',
      sampleRate: config.sampleRate || 16000,
      languageCode: config.languageCode || 'nld', // Dutch in ISO 639-3
    };
  }

  /**
   * Check if ElevenLabs STT is configured with a valid API key.
   */
  isConfigured(): boolean {
    const hasKey = Boolean(this.config.apiKey && this.config.apiKey.length > 0);
    console.log('[ElevenLabsSTT] isConfigured:', hasKey, 'keyLength:', this.config.apiKey?.length || 0);
    return hasKey;
  }

  /**
   * Fetch a single-use token from ElevenLabs API.
   * Browsers cannot set custom headers on WebSocket connections,
   * so we must use single-use tokens for authentication.
   */
  private async fetchSingleUseToken(): Promise<string> {
    const response = await fetch('https://api.elevenlabs.io/v1/single-use-token/realtime_scribe', {
      method: 'POST',
      headers: {
        'xi-api-key': this.config.apiKey,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to fetch single-use token: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    return data.token;
  }

  /**
   * Connect to ElevenLabs STT WebSocket.
   * @param actualSampleRate - The actual sample rate from AudioContext (browsers may ignore requested rate)
   */
  async connect(actualSampleRate?: number): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      console.log('[ElevenLabsSTT] Already connected or connecting');
      return;
    }

    if (!this.isConfigured()) {
      console.warn('[ElevenLabsSTT] Not configured - cannot connect');
      this.handleError(new Error('ElevenLabs API key not configured'));
      return;
    }

    this.updateStatus('connecting');

    // Use actual sample rate if provided, otherwise fall back to config
    const sampleRate = actualSampleRate || this.config.sampleRate || 16000;
    this.config.sampleRate = sampleRate;
    const audioFormat = sampleRateToAudioFormat(sampleRate);

    try {
      // Fetch a single-use token for WebSocket authentication
      // (browsers cannot set custom headers on WebSocket connections)
      console.log('[ElevenLabsSTT] Fetching single-use token...');
      const token = await this.fetchSingleUseToken();
      console.log('[ElevenLabsSTT] Single-use token obtained');

      // Build WebSocket URL with query parameters
      const url = new URL('wss://api.elevenlabs.io/v1/speech-to-text/realtime');
      url.searchParams.set('model_id', 'scribe_v2_realtime');
      url.searchParams.set('language_code', this.config.languageCode || 'nld');
      url.searchParams.set('token', token);
      // CRITICAL: Tell ElevenLabs what audio format we're sending
      url.searchParams.set('audio_format', audioFormat);
      // Use VAD-based commit so transcripts are finalized after speech pauses
      url.searchParams.set('commit_strategy', 'vad');
      // Fine-tune VAD: 1 second silence = commit (slightly faster than default 1.5s)
      url.searchParams.set('vad_silence_threshold_secs', '1.0');

      console.log(`[ElevenLabsSTT] Connecting with sampleRate=${sampleRate}, audioFormat=${audioFormat}`);

      this.ws = new WebSocket(url.toString());
      this.setupEventHandlers();
    } catch (error) {
      console.error('[ElevenLabsSTT] Failed to connect:', error);
      this.handleError(error instanceof Error ? error : new Error(`Failed to connect: ${error}`));
      this.updateStatus('error');
    }
  }

  /**
   * Disconnect from ElevenLabs STT WebSocket.
   */
  disconnect(): void {
    if (this.ws) {
      if (this.ws.readyState === WebSocket.OPEN) {
        // Send end of stream message
        this.ws.send(JSON.stringify({
          message_type: 'end_of_stream'
        }));
      }
      this.ws.close();
      this.ws = null;
    }
    this.updateStatus('disconnected');
  }

  /**
   * Send audio chunk to STT service.
   * @param base64Audio - Base64-encoded PCM 16-bit audio
   */
  sendAudioChunk(base64Audio: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        message_type: 'input_audio_chunk',
        audio_base_64: base64Audio,
        sample_rate: this.config.sampleRate,
      }));
    }
  }

  /**
   * Commit the current audio for transcription (manual commit mode).
   */
  commit(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        message_type: 'input_audio_chunk',
        audio_base_64: '',
        commit: true,
        sample_rate: this.config.sampleRate,
      }));
    }
  }

  /**
   * Subscribe to transcript events.
   */
  onTranscript(callback: TranscriptCallback): () => void {
    this.transcriptCallbacks.push(callback);
    return () => {
      this.transcriptCallbacks = this.transcriptCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * Subscribe to status changes.
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

  getStatus(): 'disconnected' | 'connecting' | 'connected' | 'error' {
    return this.currentStatus;
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[ElevenLabsSTT] WebSocket connected, waiting for session_started');
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('[ElevenLabsSTT] Received:', message.message_type);

        switch (message.message_type) {
          case 'session_started':
            console.log('[ElevenLabsSTT] Session started:', message.session_id);
            console.log('[ElevenLabsSTT] Config:', message.config);
            this.updateStatus('connected');
            break;

          case 'partial_transcript':
            // Partial (interim) transcript - not final
            if (message.text) {
              this.transcriptCallbacks.forEach((callback) => callback(message.text, false));
            }
            break;

          case 'committed_transcript':
          case 'committed_transcript_with_timestamps':
            // Final transcript
            if (message.text) {
              this.transcriptCallbacks.forEach((callback) => callback(message.text, true));
            }
            break;

          case 'error':
            console.error('[ElevenLabsSTT] Server error:', message);
            this.handleError(new Error(message.error || message.message || 'STT error'));
            break;

          case 'auth_error':
            console.error('[ElevenLabsSTT] Authentication error:', message);
            this.handleError(new Error('ElevenLabs authentication failed. The single-use token may have expired or is invalid.'));
            break;

          case 'invalid_request':
            console.error('[ElevenLabsSTT] Invalid request:', message);
            this.handleError(new Error(message.error || message.message || 'Invalid STT request'));
            break;

          default:
            console.log('[ElevenLabsSTT] Unknown message type:', message.message_type, message);
        }
      } catch (error) {
        console.error('[ElevenLabsSTT] Invalid message received:', error, event.data);
      }
    };

    this.ws.onerror = (event) => {
      console.error('[ElevenLabsSTT] WebSocket error:', event);
      this.handleError(new Error('WebSocket connection error'));
    };

    this.ws.onclose = (event) => {
      console.log(`[ElevenLabsSTT] Connection closed (code: ${event.code}, reason: ${event.reason})`);
      if (this.currentStatus === 'connected' || this.currentStatus === 'connecting') {
        this.updateStatus('disconnected');
      }
    };
  }

  private updateStatus(status: typeof this.currentStatus): void {
    this.currentStatus = status;
    this.statusCallbacks.forEach((callback) => callback(status));
  }

  private handleError(error: Error): void {
    this.updateStatus('error');
    this.errorCallbacks.forEach((callback) => callback(error));
  }
}

// Singleton instance
let sttClient: ElevenLabsSTTClient | null = null;

export function getElevenLabsSTTClient(): ElevenLabsSTTClient {
  if (!sttClient) {
    sttClient = new ElevenLabsSTTClient();
  }
  return sttClient;
}

export function resetElevenLabsSTTClient(): void {
  if (sttClient) {
    sttClient.disconnect();
    sttClient = null;
  }
}

export { ElevenLabsSTTClient };
