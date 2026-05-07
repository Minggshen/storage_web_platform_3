import React from 'react';

/** @deprecated Use Tailwind utility classes and CSS variables instead. */
const palette = {
  bg: 'var(--background)',
  card: 'var(--card)',
  border: 'var(--border)',
  text: 'var(--foreground)',
  subtext: 'var(--muted-foreground)',
  brand: 'var(--primary)',
  brandSoft: 'var(--color-info-soft)',
  success: 'var(--color-success)',
  successSoft: 'var(--color-success-soft)',
  warn: 'var(--color-warning)',
  warnSoft: 'var(--color-warning-soft)',
  danger: 'var(--color-danger)',
  dangerSoft: 'var(--color-danger-soft)',
  shadow: '0 14px 38px rgba(15, 23, 42, 0.08)',
};

/** @deprecated Use Tailwind classes: min-h-screen bg-background p-6 */
export function pageShellStyle(): React.CSSProperties {
  return { minHeight: '100%', padding: 24, background: palette.bg };
}

/** @deprecated Use Tailwind classes: rounded-2xl border border-border bg-card p-5 shadow-sm */
export function panelStyle(extra?: React.CSSProperties): React.CSSProperties {
  return { background: palette.card, border: `1px solid ${palette.border}`, borderRadius: 18, boxShadow: palette.shadow, ...extra };
}

/** @deprecated Use Tailwind classes: p-4.5 */
export function sectionBodyStyle(extra?: React.CSSProperties): React.CSSProperties {
  return { padding: 18, ...extra };
}

/** @deprecated Use Tailwind classes: text-4xl / text-2xl / text-lg font-extrabold tracking-tight text-foreground */
export function headingStyle(level: 1 | 2 | 3 = 1): React.CSSProperties {
  const size = level === 1 ? 36 : level === 2 ? 24 : 18;
  return { margin: 0, fontSize: size, fontWeight: 800, color: palette.text, letterSpacing: '-0.02em' };
}

/** @deprecated Use Tailwind classes: text-sm text-muted-foreground */
export function subtextStyle(extra?: React.CSSProperties): React.CSSProperties {
  return { color: palette.subtext, fontSize: 14, lineHeight: 1.7, ...extra };
}

/** @deprecated Use shadcn/ui <Button variant="default|outline|ghost"> */
export function buttonStyle(kind: 'primary' | 'secondary' | 'ghost' = 'secondary'): React.CSSProperties {
  const base: React.CSSProperties = { borderRadius: 12, padding: '10px 16px', fontSize: 14, fontWeight: 700, cursor: 'pointer', transition: 'all 0.2s ease' };
  if (kind === 'primary') return { ...base, border: `1px solid ${palette.brand}`, background: palette.brand, color: '#fff' };
  if (kind === 'ghost') return { ...base, border: '1px solid transparent', background: 'transparent', color: palette.brand };
  return { ...base, border: `1px solid ${palette.border}`, background: '#fff', color: palette.text };
}

/** @deprecated Use <StatusBadge> component */
export function statusChip(status: string | null | undefined): React.CSSProperties {
  const normalized = String(status || 'unknown').toLowerCase();
  let bg = palette.brandSoft; let color = palette.brand;
  if (['completed', 'done', 'ready', 'success'].includes(normalized)) { bg = palette.successSoft; color = palette.success; }
  else if (['failed', 'error'].includes(normalized)) { bg = palette.dangerSoft; color = palette.danger; }
  else if (['running', 'queued', 'doing'].includes(normalized)) { bg = palette.warnSoft; color = palette.warn; }
  return { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 999, background: bg, color, fontWeight: 700, fontSize: 12 };
}

/** @deprecated Use <SectionCard> component */
export function cardTitle(title: string, extra?: React.ReactNode) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
      <h2 style={headingStyle(3)}>{title}</h2>
      {extra}
    </div>
  );
}

/** @deprecated Use <MetricGrid> component */
export function MetricCard(props: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div style={{ ...panelStyle(), padding: 16 }}>
      <div style={{ ...subtextStyle(), fontSize: 13 }}>{props.label}</div>
      <div style={{ marginTop: 8, fontSize: 26, fontWeight: 800, color: palette.text }}>{props.value}</div>
      {props.hint ? <div style={{ ...subtextStyle(), marginTop: 8 }}>{props.hint}</div> : null}
    </div>
  );
}

/** @deprecated Use <EmptyState> component */
export function EmptyBlock(props: { title: string; description?: string }) {
  return (
    <div style={{ ...panelStyle(), padding: 18, borderStyle: 'dashed', background: '#fbfdff', color: palette.subtext }}>
      <div style={{ fontWeight: 700, color: palette.text }}>{props.title}</div>
      {props.description ? <div style={{ ...subtextStyle(), marginTop: 6 }}>{props.description}</div> : null}
    </div>
  );
}

/** @deprecated Use Tailwind grid classes */
export function LabelValue(props: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: 12, padding: '6px 0' }}>
      <div style={{ ...subtextStyle(), fontSize: 13 }}>{props.label}</div>
      <div style={{ color: palette.text, fontWeight: 600, wordBreak: 'break-word' }}>{props.value}</div>
    </div>
  );
}

export const uiPalette = palette;


// ── Tailwind class string helpers (preferred) ──

/** Tailwind class string for page-level headings */
export function headingClasses(level: 1 | 2 | 3 = 1): string {
  const sizes: Record<number, string> = { 1: 'text-4xl', 2: 'text-2xl', 3: 'text-lg' };
  return `${sizes[level]} font-extrabold tracking-tight text-foreground`;
}

/** Tailwind class string for card panels */
export const panelClasses = 'rounded-2xl border border-border bg-card p-5 shadow-xs';

/** Tailwind class string for page shell */
export const pageShellClasses = 'min-h-screen bg-background p-6';
