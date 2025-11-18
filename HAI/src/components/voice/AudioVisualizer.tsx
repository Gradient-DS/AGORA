import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface AudioVisualizerProps {
  isActive: boolean;
  volume?: number;
  className?: string;
}

export function AudioVisualizer({ 
  isActive, 
  volume = 0, 
  className 
}: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      const width = canvas.width;
      const height = canvas.height;

      ctx.clearRect(0, 0, width, height);

      if (isActive) {
        const barCount = 50;
        const barWidth = width / barCount;
        const centerY = height / 2;

        for (let i = 0; i < barCount; i++) {
          const barHeight = Math.random() * volume * height * 0.5 + 5;
          const x = i * barWidth;
          
          ctx.fillStyle = 'hsl(var(--primary))';
          ctx.fillRect(x, centerY - barHeight / 2, barWidth - 2, barHeight);
        }
      }

      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isActive, volume]);

  return (
    <div className={cn('relative w-full h-32 bg-muted rounded-lg overflow-hidden', className)}>
      <canvas
        ref={canvasRef}
        width={800}
        height={128}
        className="w-full h-full"
        aria-label="Audio visualisatie"
      />
      {!isActive && (
        <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
          <p>Start spraak modus om audio visualisatie te zien</p>
        </div>
      )}
    </div>
  );
}

