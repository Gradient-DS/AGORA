import { useApprovalStore } from '@/stores';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertCircle } from 'lucide-react';

export function ApprovalQueue() {
  const pendingApprovals = useApprovalStore((state) => state.pendingApprovals);
  const currentApproval = useApprovalStore((state) => state.currentApproval);

  if (pendingApprovals.length === 0) {
    return null;
  }

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          Pending Approvals
          <Badge variant="secondary">{pendingApprovals.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {pendingApprovals.map((approval) => (
            <div
              key={approval.approval_id}
              className={`text-sm p-2 rounded border ${
                currentApproval?.approval_id === approval.approval_id
                  ? 'border-primary bg-primary/10'
                  : 'border-border'
              }`}
            >
              <span className="font-medium">{approval.tool_name}</span>
              <Badge 
                variant={approval.risk_level === 'critical' || approval.risk_level === 'high' ? 'destructive' : 'default'}
                className="ml-2 text-xs"
              >
                {approval.risk_level}
              </Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

