import { Component, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    if (this.props.onError) {
      this.props.onError(error);
    }
    if (import.meta.env.DEV) {
      console.error('[ErrorBoundary]', error, info.componentStack);
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          role="alert"
          className={cn(
            'rounded-xl border border-red-500/30 bg-red-500/10 p-6',
            'flex flex-col items-start gap-3',
          )}
        >
          <div className="text-sm font-semibold text-red-600">
            页面发生异常
          </div>
          {this.state.error && (
            <pre className="max-h-40 w-full overflow-auto rounded-lg bg-red-50/50 px-3 py-2 text-xs text-red-500">
              {this.state.error.message}
            </pre>
          )}
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            className={cn(
              'rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white',
              'hover:bg-red-700 transition-colors',
            )}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
