import { cn } from '@/lib/utils';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={cn(
        'mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5',
        'flex items-start justify-between gap-3',
      )}
    >
      <span className="text-sm text-red-600">
        加载失败：{message}
      </span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-lg bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 transition-colors"
        >
          重试
        </button>
      )}
    </div>
  );
}
