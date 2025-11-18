import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Mic, MicOff } from 'lucide-react';

interface VoiceButtonProps {
  isActive: boolean;
  isListening: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function VoiceButton({ 
  isActive, 
  isListening, 
  onToggle, 
  disabled = false 
}: VoiceButtonProps) {
  return (
    <Button
      onClick={onToggle}
      disabled={disabled}
      size="lg"
      variant={isActive ? 'default' : 'outline'}
      className={cn(
        'w-full h-20 text-lg',
        isListening && 'animate-pulse-slow'
      )}
      aria-label={isActive ? 'Stop spraak modus' : 'Start spraak modus'}
      aria-pressed={isActive}
    >
      {isActive ? (
        <>
          <MicOff className="mr-2 h-6 w-6" aria-hidden="true" />
          Stop Spraak
        </>
      ) : (
        <>
          <Mic className="mr-2 h-6 w-6" aria-hidden="true" />
          Start Spraak
        </>
      )}
    </Button>
  );
}

