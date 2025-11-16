import { Button } from '@/components/ui/button';
import { Download, FileJson, FileText } from 'lucide-react';
import { Card } from '@/components/ui/card';

interface DownloadLinksProps {
  jsonUrl?: string;
  pdfUrl?: string;
  reportId?: string;
}

export function DownloadLinks({ jsonUrl, pdfUrl, reportId }: DownloadLinksProps) {
  if (!jsonUrl && !pdfUrl) return null;

  return (
    <Card className="p-4 bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 border-blue-200 dark:border-blue-800">
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0">
          <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center">
            <Download className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          </div>
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-1">
            Rapport Gereed
          </h4>
          <p className="text-xs text-blue-700 dark:text-blue-300 mb-2">
            {reportId ? `Rapport ${reportId} is succesvol gegenereerd` : 'Uw rapport is klaar om te downloaden'}
          </p>
          <div className="flex gap-2">
            {jsonUrl && (
              <Button
                size="sm"
                variant="outline"
                className="text-xs bg-white dark:bg-gray-800 hover:bg-blue-50 dark:hover:bg-blue-900/50"
                onClick={() => window.open(jsonUrl, '_blank')}
              >
                <FileJson className="h-3.5 w-3.5 mr-1" />
                Download JSON
              </Button>
            )}
            {pdfUrl && (
              <Button
                size="sm"
                className="text-xs bg-blue-600 hover:bg-blue-700 text-white"
                onClick={() => window.open(pdfUrl, '_blank')}
              >
                <FileText className="h-3.5 w-3.5 mr-1" />
                Download PDF
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

