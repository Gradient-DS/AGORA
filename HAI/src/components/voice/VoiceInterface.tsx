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
    if (!isActive) return 'Voice mode inactive';
    if (isSpeaking) return 'Assistant is speaking...';
    if (isListening) return 'Listening...';
    return 'Voice mode active';
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader>
        <CardTitle>Voice Interface</CardTitle>
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
          aria-label="Voice status"
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

