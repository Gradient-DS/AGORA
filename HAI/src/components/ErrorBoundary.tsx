import { Component, ErrorInfo, ReactNode } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { AlertCircle } from 'lucide-react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({
      hasError: false,
      error: null,
    });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-background">
          <div className="max-w-md w-full space-y-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Er is iets misgegaan</AlertTitle>
              <AlertDescription>
                {this.state.error?.message || 'Er is een onverwachte fout opgetreden'}
              </AlertDescription>
            </Alert>

            <div className="flex gap-2">
              <Button onClick={this.handleReset} className="flex-1">
                Probeer Opnieuw
              </Button>
              <Button 
                variant="outline" 
                onClick={() => window.location.reload()}
                className="flex-1"
              >
                Pagina Herladen
              </Button>
            </div>

            {import.meta.env.DEV && this.state.error && (
              <details className="mt-4 p-4 bg-muted rounded-lg">
                <summary className="cursor-pointer font-semibold">Fout Details</summary>
                <pre className="mt-2 text-xs overflow-auto">
                  {this.state.error.stack}
                </pre>
              </details>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

