/**
 * TTS Toggle component for AGORA HAI.
 *
 * Simple button to enable/disable ElevenLabs text-to-speech.
 */

import { Button } from '@/components/ui/button';
import { Volume2, VolumeX } from 'lucide-react';
import { useTTSStore } from '@/stores';
import { getElevenLabsClient } from '@/lib/elevenlabs';
import { cn } from '@/lib/utils';

interface TTSToggleProps {
  disabled?: boolean;
  className?: string;
}

export function TTSToggle({ disabled = false, className }: TTSToggleProps) {
  const isEnabled = useTTSStore((state) => state.isEnabled);
  const isSpeaking = useTTSStore((state) => state.isSpeaking);
  const toggleEnabled = useTTSStore((state) => state.toggleEnabled);

  const client = getElevenLabsClient();
  const isConfigured = client.isConfigured();

  // Don't render if ElevenLabs is not configured
  if (!isConfigured) {
    return null;
  }

  const handleClick = () => {
    if (isEnabled) {
      // Stop any current playback when disabling
      client.stop();
    }
    toggleEnabled();
  };

  return (
    <Button
      onClick={handleClick}
      disabled={disabled}
      size="icon"
      variant={isEnabled ? 'default' : 'outline'}
      className={cn(
        'h-[60px] w-[60px] flex-shrink-0',
        isEnabled && 'bg-primary',
        isSpeaking && 'animate-pulse',
        className
      )}
      aria-label={isEnabled ? 'Schakel voorlezen uit' : 'Schakel voorlezen in'}
      aria-pressed={isEnabled}
      title={isEnabled ? 'Voorlezen uit' : 'Voorlezen aan'}
    >
      {isEnabled ? (
        <Volume2 className="h-5 w-5" aria-hidden="true" />
      ) : (
        <VolumeX className="h-5 w-5" aria-hidden="true" />
      )}
    </Button>
  );
}
