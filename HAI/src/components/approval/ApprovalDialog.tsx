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
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import type { ToolApprovalRequest, RiskLevel } from '@/types/schemas';

interface ApprovalDialogProps {
  approval: ToolApprovalRequest;
  onApprove: (approvalId: string, feedback?: string) => void;
  onReject: (approvalId: string, feedback?: string) => void;
}

const riskLevelConfig: Record<RiskLevel, { color: string; icon: typeof AlertCircle }> = {
  low: { color: 'bg-green-500', icon: CheckCircle },
  medium: { color: 'bg-yellow-500', icon: AlertCircle },
  high: { color: 'bg-orange-500', icon: AlertCircle },
  critical: { color: 'bg-red-500', icon: XCircle },
};

export function ApprovalDialog({ approval, onApprove, onReject }: ApprovalDialogProps) {
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleApprove = async () => {
    setIsSubmitting(true);
    await onApprove(approval.approval_id, feedback || undefined);
    setIsSubmitting(false);
  };

  const handleReject = async () => {
    setIsSubmitting(true);
    await onReject(approval.approval_id, feedback || undefined);
    setIsSubmitting(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleApprove();
    } else if (e.key === 'Escape') {
      handleReject();
    }
  };

  const RiskIcon = riskLevelConfig[approval.risk_level].icon;

  return (
    <Card 
      className="max-w-2xl mx-auto"
      role="dialog"
      aria-labelledby="approval-title"
      aria-describedby="approval-description"
      onKeyDown={handleKeyDown}
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
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div>
          <h4 className="text-sm font-semibold mb-2">Reasoning</h4>
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
            Feedback (Optional)
          </label>
          <Textarea
            id="feedback"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Add any feedback or comments..."
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
          aria-label="Reject tool execution"
        >
          <XCircle className="h-4 w-4 mr-2" aria-hidden="true" />
          Reject
        </Button>
        <Button
          onClick={handleApprove}
          disabled={isSubmitting}
          aria-label="Approve tool execution"
        >
          <CheckCircle className="h-4 w-4 mr-2" aria-hidden="true" />
          Approve
        </Button>
      </CardFooter>

      <div className="px-6 pb-4 text-xs text-muted-foreground">
        Keyboard shortcuts: <kbd>Enter</kbd> to approve, <kbd>Esc</kbd> to reject
      </div>
    </Card>
  );
}

