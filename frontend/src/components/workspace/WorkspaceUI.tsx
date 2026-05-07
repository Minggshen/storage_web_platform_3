import React from 'react';

const palette = {
  bg: '#f3f6fb',
  card: '#ffffff',
  border: '#d8e1f0',
  text: '#132238',
  subtext: '#5b6b84',
  brand: '#1d4ed8',
  brandSoft: '#e8f0ff',
  success: '#15803d',
  successSoft: '#dcfce7',
  warn: '#b45309',
  warnSoft: '#ffedd5',
  danger: '#b91c1c',
  dangerSoft: '#fee2e2',
  shadow: '0 14px 38px rgba(15, 23, 42, 0.08)',
};

export function pageShellStyle(): React.CSSProperties {
  return {
    minHeight: '100%',
    padding: 24,
    background: palette.bg,
  };
}

export function panelStyle(extra?: React.CSSProperties): React.CSSProperties {
  return {
    background: palette.card,
    border: `1px solid ${palette.border}`,
    borderRadius: 18,
    boxShadow: palette.shadow,
    ...extra,
  };
}

export function sectionBodyStyle(extra?: React.CSSProperties): React.CSSProperties {
  return {
    padding: 18,
    ...extra,
  };
}

export function headingStyle(level: 1 | 2 | 3 = 1): React.CSSProperties {
  const size = level === 1 ? 36 : level === 2 ? 24 : 18;
  return {
    margin: 0,
    fontSize: size,
    fontWeight: 800,
    color: palette.text,
    letterSpacing: '-0.02em',
  };
}

export function subtextStyle(extra?: React.CSSProperties): React.CSSProperties {
  return {
    color: palette.subtext,
    fontSize: 14,
    lineHeight: 1.7,
    ...extra,
  };
}

export function buttonStyle(kind: 'primary' | 'secondary' | 'ghost' = 'secondary'): React.CSSProperties {
  const base: React.CSSProperties = {
    borderRadius: 12,
    padding: '10px 16px',
    fontSize: 14,
    fontWeight: 700,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  };
  if (kind === 'primary') {
    return {
      ...base,
      border: `1px solid ${palette.brand}`,
      background: palette.brand,
      color: '#fff',
    };
  }
  if (kind === 'ghost') {
    return {
      ...base,
      border: `1px solid transparent`,
      background: 'transparent',
      color: palette.brand,
    };
  }
  return {
    ...base,
    border: `1px solid ${palette.border}`,
    background: '#fff',
    color: palette.text,
  };
}

export function statusChip(status: string | null | undefined): React.CSSProperties {
  const normalized = String(status || 'unknown').toLowerCase();
  let bg = palette.brandSoft;
  let color = palette.brand;

  if (['completed', 'done', 'ready', 'success'].includes(normalized)) {
    bg = palette.successSoft;
    color = palette.success;
  } else if (['failed', 'error'].includes(normalized)) {
    bg = palette.dangerSoft;
    color = palette.danger;
  } else if (['running', 'queued', 'doing'].includes(normalized)) {
    bg = palette.warnSoft;
    color = palette.warn;
  }

  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 10px',
    borderRadius: 999,
    background: bg,
    color,
    fontWeight: 700,
    fontSize: 12,
  };
}

export function cardTitle(title: string, extra?: React.ReactNode) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
      <h2 style={headingStyle(3)}>{title}</h2>
      {extra}
    </div>
  );
}

export function MetricCard(props: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div style={{ ...panelStyle(), padding: 16 }}>
      <div style={{ ...subtextStyle(), fontSize: 13 }}>{props.label}</div>
      <div style={{ marginTop: 8, fontSize: 26, fontWeight: 800, color: palette.text }}>{props.value}</div>
      {props.hint ? <div style={{ ...subtextStyle(), marginTop: 8 }}>{props.hint}</div> : null}
    </div>
  );
}

export function EmptyBlock(props: { title: string; description?: string }) {
  return (
    <div style={{
      ...panelStyle(),
      padding: 18,
      borderStyle: 'dashed',
      background: '#fbfdff',
      color: palette.subtext,
    }}>
      <div style={{ fontWeight: 700, color: palette.text }}>{props.title}</div>
      {props.description ? <div style={{ ...subtextStyle(), marginTop: 6 }}>{props.description}</div> : null}
    </div>
  );
}

export function LabelValue(props: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: 12, padding: '6px 0' }}>
      <div style={{ ...subtextStyle(), fontSize: 13 }}>{props.label}</div>
      <div style={{ color: palette.text, fontWeight: 600, wordBreak: 'break-word' }}>{props.value}</div>
    </div>
  );
}

export const uiPalette = palette;
