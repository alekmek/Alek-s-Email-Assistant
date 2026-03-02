import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-8">
          <div className="max-w-2xl w-full bg-red-900/50 border border-red-500 rounded-xl p-6">
            <h1 className="text-2xl font-bold text-red-400 mb-4">Something went wrong</h1>

            <div className="bg-slate-800 rounded-lg p-4 mb-4 overflow-auto max-h-64">
              <p className="text-red-300 font-mono text-sm whitespace-pre-wrap">
                {this.state.error?.toString()}
              </p>
              {this.state.errorInfo && (
                <pre className="text-slate-400 font-mono text-xs mt-4 whitespace-pre-wrap">
                  {this.state.errorInfo.componentStack}
                </pre>
              )}
            </div>

            <div className="flex gap-4">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
              >
                Reload App
              </button>
              <button
                onClick={() => {
                  const text = `Error: ${this.state.error?.toString()}\n\nStack: ${this.state.errorInfo?.componentStack}`;
                  navigator.clipboard.writeText(text);
                }}
                className="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg font-medium transition-colors"
              >
                Copy Error
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
