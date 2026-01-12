import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, Mic, MicOff, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TTSToggle } from './TTSToggle';
import { useVoiceStore } from '@/stores';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  onToggleVoice?: () => void;
  isVoiceActive?: boolean;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Typ uw bericht...',
  onToggleVoice,
  isVoiceActive = false
}: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const partialTranscript = useVoiceStore((state) => state.partialTranscript);
  const isListening = useVoiceStore((state) => state.isListening);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message.trim());
      setMessage('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Show partial transcript or regular placeholder
  const displayPlaceholder = isVoiceActive && isListening
    ? (partialTranscript || 'Luisteren...')
    : placeholder;

  return (
    <div className="flex flex-col gap-2">
      {/* Voice status indicator */}
      {isVoiceActive && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted/50 px-3 py-2 rounded-md">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          <span>
            {partialTranscript
              ? `Transcriptie: "${partialTranscript}"`
              : 'Luisteren naar spraak...'}
          </span>
        </div>
      )}

      <div className="flex gap-2 items-end">
        {onToggleVoice && (
          <Button
            onClick={onToggleVoice}
            disabled={disabled}
            size="icon"
            variant={isVoiceActive ? 'default' : 'outline'}
            className={cn(
              'h-[60px] w-[60px] flex-shrink-0',
              isVoiceActive && 'bg-primary animate-pulse'
            )}
            aria-label={isVoiceActive ? 'Stop spraak modus' : 'Start spraak modus'}
            aria-pressed={isVoiceActive}
          >
            {isVoiceActive ? (
              <MicOff className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Mic className="h-5 w-5" aria-hidden="true" />
            )}
          </Button>
        )}
        <TTSToggle disabled={disabled} />
        <Textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={displayPlaceholder}
          disabled={disabled || isVoiceActive}
          className={cn(
            "min-h-[60px] max-h-[200px] resize-none",
            isVoiceActive && "bg-muted/50"
          )}
          aria-label="Bericht invoer"
        />
        <Button
          onClick={handleSend}
          disabled={disabled || !message.trim() || isVoiceActive}
          size="icon"
          className="h-[60px] w-[60px] flex-shrink-0"
          aria-label="Verstuur bericht"
        >
          <Send className="h-5 w-5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
