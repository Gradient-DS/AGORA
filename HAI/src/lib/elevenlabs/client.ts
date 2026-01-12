/**
 * ElevenLabs TTS client for AGORA HAI.
 *
 * Lightweight client for text-to-speech using ElevenLabs streaming API.
 * Manages audio playback queue for sequential speech.
 */

import { getElevenLabsApiKey, getElevenLabsVoiceId } from '@/lib/env';

interface ElevenLabsConfig {
  apiKey: string;
  voiceId: string;
  modelId?: string;
  stability?: number;
  similarityBoost?: number;
}

interface QueueItem {
  text: string;
  resolve: () => void;
  reject: (error: Error) => void;
}

class ElevenLabsClient {
  private config: ElevenLabsConfig;
  private queue: QueueItem[] = [];
  private isProcessing = false;
  private currentAudio: HTMLAudioElement | null = null;

  constructor(config: Partial<ElevenLabsConfig> = {}) {
    this.config = {
      apiKey: config.apiKey || getElevenLabsApiKey(),
      voiceId: config.voiceId || getElevenLabsVoiceId(),
      modelId: config.modelId || 'eleven_multilingual_v2',
      stability: config.stability ?? 0.5,
      similarityBoost: config.similarityBoost ?? 0.75,
    };
  }

  /**
   * Check if ElevenLabs is configured with a valid API key.
   */
  isConfigured(): boolean {
    return Boolean(this.config.apiKey && this.config.apiKey.length > 0);
  }

  /**
   * Queue text to be spoken. Returns a promise that resolves when playback completes.
   */
  async speak(text: string): Promise<void> {
    if (!this.isConfigured()) {
      return;
    }

    if (!text || text.trim().length === 0) {
      return;
    }

    return new Promise((resolve, reject) => {
      this.queue.push({ text: text.trim(), resolve, reject });
      this.processQueue();
    });
  }

  /**
   * Stop current playback and clear the queue.
   */
  stop(): void {
    // Clear queue
    this.queue.forEach(item => item.resolve());
    this.queue = [];

    // Stop current audio
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.src = '';
      this.currentAudio = null;
    }

    this.isProcessing = false;
  }

  private async processQueue(): Promise<void> {
    if (this.isProcessing || this.queue.length === 0) {
      return;
    }

    this.isProcessing = true;
    const item = this.queue.shift()!;

    try {
      await this.playText(item.text);
      item.resolve();
    } catch (error) {
      item.reject(error instanceof Error ? error : new Error('Playback failed'));
    } finally {
      this.isProcessing = false;
      // Process next item in queue
      if (this.queue.length > 0) {
        this.processQueue();
      }
    }
  }

  private async playText(text: string): Promise<void> {
    const url = `https://api.elevenlabs.io/v1/text-to-speech/${this.config.voiceId}/stream`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'xi-api-key': this.config.apiKey,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        model_id: this.config.modelId,
        voice_settings: {
          stability: this.config.stability,
          similarity_boost: this.config.similarityBoost,
        },
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`ElevenLabs API error: ${response.status} - ${errorText}`);
    }

    // Convert response to blob and play
    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);

    return new Promise((resolve, reject) => {
      const audio = new Audio(audioUrl);
      this.currentAudio = audio;

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        this.currentAudio = null;
        resolve();
      };

      audio.onerror = (e) => {
        URL.revokeObjectURL(audioUrl);
        this.currentAudio = null;
        reject(new Error(`Audio playback error: ${e}`));
      };

      audio.play().catch(reject);
    });
  }
}

// Singleton instance
let client: ElevenLabsClient | null = null;

export function getElevenLabsClient(): ElevenLabsClient {
  if (!client) {
    client = new ElevenLabsClient();
  }
  return client;
}

export function resetElevenLabsClient(): void {
  if (client) {
    client.stop();
    client = null;
  }
}

export { ElevenLabsClient };
