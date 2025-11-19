import { useState } from 'react';
import { 
  Card, 
  CardContent, 
  CardDescription, 
  CardFooter, 
  CardHeader, 
  CardTitle 
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { AlertCircle, CheckCircle, XCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import type { ToolApprovalRequest, RiskLevel } from '@/types/schemas';

interface ApprovalDialogProps {
  approval: ToolApprovalRequest;
  onApprove: (approvalId: string, feedback?: string) => void;
  onReject: (approvalId: string, feedback?: string) => void;
  currentIndex: number;
  totalCount: number;
  onNavigate: (direction: 'next' | 'prev') => void;
}

const riskLevelConfig: Record<RiskLevel, { color: string; icon: typeof AlertCircle }> = {
  low: { color: 'bg-green-500', icon: CheckCircle },
  medium: { color: 'bg-yellow-500', icon: AlertCircle },
  high: { color: 'bg-orange-500', icon: AlertCircle },
  critical: { color: 'bg-red-500', icon: XCircle },
};

export function ApprovalDialog({ 
  approval, 
  onApprove, 
  onReject,
  currentIndex,
  totalCount,
  onNavigate
}: ApprovalDialogProps) {
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleApprove = async () => {
    setIsSubmitting(true);
    await onApprove(approval.approval_id, feedback || undefined);
    setIsSubmitting(false);
    setFeedback('');
  };

  const handleReject = async () => {
    setIsSubmitting(true);
    await onReject(approval.approval_id, feedback || undefined);
    setIsSubmitting(false);
    setFeedback('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleApprove();
    } else if (e.key === 'Escape') {
      handleReject();
    } else if (e.key === 'ArrowLeft' && !isSubmitting) {
      if (currentIndex > 0) onNavigate('prev');
    } else if (e.key === 'ArrowRight' && !isSubmitting) {
      if (currentIndex < totalCount - 1) onNavigate('next');
    }
  };

  const RiskIcon = riskLevelConfig[approval.risk_level].icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <Card 
        className="w-full max-w-2xl shadow-xl max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-labelledby="approval-title"
        aria-describedby="approval-description"
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <CardTitle id="approval-title" className="flex items-center gap-2">
                {approval.tool_name}
                <Badge 
                  variant={approval.risk_level === 'critical' || approval.risk_level === 'high' ? 'destructive' : 'default'}
                  className="ml-2"
                >
                  <RiskIcon className="h-3 w-3 mr-1" aria-hidden="true" />
                  {approval.risk_level.toUpperCase()}
                </Badge>
              </CardTitle>
              <CardDescription id="approval-description">
                {approval.tool_description}
              </CardDescription>
            </div>
            
            {totalCount > 1 && (
              <div className="flex items-center gap-1 bg-muted/50 rounded-md p-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onNavigate('prev')}
                  disabled={currentIndex === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm font-medium min-w-[3rem] text-center">
                  {currentIndex + 1} / {totalCount}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => onNavigate('next')}
                  disabled={currentIndex === totalCount - 1}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </CardHeader>

      <CardContent className="space-y-4">
        <div>
          <h4 className="text-sm font-semibold mb-2">Redenering</h4>
          <p className="text-sm text-muted-foreground">{approval.reasoning}</p>
        </div>

        <Separator />

        <div>
          <h4 className="text-sm font-semibold mb-2">Parameters</h4>
          <div className="bg-muted rounded-md p-3 text-sm font-mono">
            <pre className="whitespace-pre-wrap break-words">
              {JSON.stringify(approval.parameters, null, 2)}
            </pre>
          </div>
        </div>

        <Separator />

        <div>
          <label htmlFor="feedback" className="text-sm font-semibold mb-2 block">
            Feedback (Optioneel)
          </label>
          <Textarea
            id="feedback"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Voeg eventuele feedback of opmerkingen toe..."
            className="min-h-[80px]"
            disabled={isSubmitting}
          />
        </div>
      </CardContent>

      <CardFooter className="flex justify-end gap-2">
        <Button
          variant="outline"
          onClick={handleReject}
          disabled={isSubmitting}
          aria-label="Weiger tool uitvoering"
        >
          <XCircle className="h-4 w-4 mr-2" aria-hidden="true" />
          Weigeren
        </Button>
        <Button
          onClick={handleApprove}
          disabled={isSubmitting}
          aria-label="Goedkeuren tool uitvoering"
        >
          <CheckCircle className="h-4 w-4 mr-2" aria-hidden="true" />
          Goedkeuren
        </Button>
      </CardFooter>

      <div className="px-6 pb-4 text-xs text-muted-foreground">
        Toetsenbord sneltoetsen: <kbd>Enter</kbd> om goed te keuren, <kbd>Esc</kbd> om te weigeren
      </div>
      </Card>
    </div>
  );
}

