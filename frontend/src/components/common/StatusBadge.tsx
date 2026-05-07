const statusClassMap: Record<string, string> = {
  completed: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  succeeded: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  done: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  running: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
  in_progress: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
  queued: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
  ready: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
  failed: 'bg-red-500/10 text-red-600 border-red-500/30',
  not_started: 'bg-muted text-muted-foreground border-border',
  todo: 'bg-muted text-muted-foreground border-border',
};

export function StatusBadge({ value }: { value?: string | null }) {
  const normalized = value ?? 'unknown';
  const cls = statusClassMap[normalized] ?? 'bg-muted text-muted-foreground border-border';
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>
      {normalized}
    </span>
  );
}
