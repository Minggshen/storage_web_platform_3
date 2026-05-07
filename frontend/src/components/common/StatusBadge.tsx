const statusClassMap: Record<string, string> = {
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  succeeded: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  done: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  running: 'bg-sky-50 text-sky-700 border-sky-200',
  queued: 'bg-amber-50 text-amber-700 border-amber-200',
  ready: 'bg-violet-50 text-violet-700 border-violet-200',
  failed: 'bg-rose-50 text-rose-700 border-rose-200',
  not_started: 'bg-slate-50 text-slate-600 border-slate-200',
  todo: 'bg-slate-50 text-slate-600 border-slate-200',
};

export function StatusBadge({ value }: { value?: string | null }) {
  const normalized = value ?? 'unknown';
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusClassMap[normalized] ?? 'bg-slate-50 text-slate-600 border-slate-200'}`}>
      {normalized}
    </span>
  );
}
