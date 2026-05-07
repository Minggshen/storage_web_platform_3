/** Semantic status color → Tailwind class mappings */
export const statusClasses = {
  completed: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  succeeded: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  running: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
  in_progress: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
  failed: 'bg-red-500/10 text-red-600 border-red-500/30',
  queued: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
  pending: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
  not_started: 'bg-muted text-muted-foreground border-border',
} as const;

/** Common layout class compositions */
export const layoutClasses = {
  pageShell: 'min-h-screen bg-background p-6',
  pageInner: 'mx-auto max-w-[1440px] space-y-6',
  sectionsGrid: 'grid grid-cols-1 gap-6 lg:grid-cols-2',
  metricsGrid: 'grid gap-4 sm:grid-cols-2 xl:grid-cols-4',
} as const;

/** Step status → solid color (for numbered step indicators) */
export const stepStatusColor = {
  completed: { bg: 'var(--color-success)', text: '#fff' },
  in_progress: { bg: 'var(--color-info)', text: '#fff' },
  failed: { bg: 'var(--color-danger)', text: '#fff' },
  not_started: { bg: 'var(--muted)', text: 'var(--muted-foreground)' },
} as const;
