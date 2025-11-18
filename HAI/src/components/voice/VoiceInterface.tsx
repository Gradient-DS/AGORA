import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { VoiceButton } from './VoiceButton';
import { AudioVisualizer } from './AudioVisualizer';
import { useVoiceStore } from '@/stores';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { User } from 'lucide-react';

interface VoiceInterfaceProps {
  onToggleVoice: () => void;
  disabled?: boolean;
}

export function VoiceInterface({ onToggleVoice, disabled = false }: VoiceInterfaceProps) {
  const { isActive, isListening, isSpeaking, volume } = useVoiceStore();

  const getStatusText = () => {
    if (!isActive) return 'Spraak modus inactief';
    if (isSpeaking) return 'Assistent is aan het spreken...';
    if (isListening) return 'Aan het luisteren...';
    return 'Spraak modus actief';
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader>
        <CardTitle>Spraak Interface</CardTitle>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col justify-center items-center space-y-6">
        <div className="relative">
          <Avatar className="h-32 w-32">
            <AvatarFallback className="bg-primary text-primary-foreground">
              <User className="h-16 w-16" aria-hidden="true" />
            </AvatarFallback>
          </Avatar>
          {isListening && (
            <div className="absolute inset-0 rounded-full border-4 border-primary animate-ping" />
          )}
        </div>

        <div 
          className="text-center"
          role="status"
          aria-live="polite"
          aria-label="Spraak status"
        >
          <p className="text-lg font-medium">{getStatusText()}</p>
        </div>

        <AudioVisualizer 
          isActive={isActive} 
          volume={volume}
          className="w-full"
        />

        <VoiceButton
          isActive={isActive}
          isListening={isListening}
          onToggle={onToggleVoice}
          disabled={disabled}
        />
      </CardContent>
    </Card>
  );
}

