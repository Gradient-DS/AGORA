import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, Mic, MicOff } from 'lucide-react';
import { cn } from '@/lib/utils';

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

  return (
    <div className="flex gap-2 items-end">
      {onToggleVoice && (
        <Button
          onClick={onToggleVoice}
          disabled={disabled}
          size="icon"
          variant={isVoiceActive ? 'default' : 'outline'}
          className={cn(
            'h-[60px] w-[60px] flex-shrink-0',
            isVoiceActive && 'bg-primary'
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
      <Textarea
        ref={textareaRef}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        className="min-h-[60px] max-h-[200px] resize-none"
        aria-label="Bericht invoer"
      />
      <Button
        onClick={handleSend}
        disabled={disabled || !message.trim()}
        size="icon"
        className="h-[60px] w-[60px] flex-shrink-0"
        aria-label="Verstuur bericht"
      >
        <Send className="h-5 w-5" aria-hidden="true" />
      </Button>
    </div>
  );
}

