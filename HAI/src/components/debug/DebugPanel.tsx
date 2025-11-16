import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Activity, Zap } from 'lucide-react';

export function DebugPanel() {
  return (
    <Card className="h-full flex flex-col overflow-hidden">
      <CardHeader className="flex-shrink-0">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Monitor
          </CardTitle>
          <Badge variant="outline" className="gap-1">
            <Zap className="h-3 w-3" />
            Active
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto space-y-4">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground">Agent Activity</h3>
          <div className="p-4 rounded-lg bg-muted/50 text-sm">
            <p className="text-muted-foreground">Waiting for agent activity...</p>
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground">Routing Information</h3>
          <div className="p-4 rounded-lg bg-muted/50 text-sm">
            <p className="text-muted-foreground">No routing data available</p>
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground">Tool Execution</h3>
          <div className="p-4 rounded-lg bg-muted/50 text-sm">
            <p className="text-muted-foreground">No tool executions yet</p>
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-muted-foreground">Session Info</h3>
          <div className="p-4 rounded-lg bg-muted/50 text-sm space-y-1">
            <p className="text-muted-foreground">Session active</p>
            <p className="text-xs text-muted-foreground/70">This panel will show real-time system activity</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

