import React from 'react';

type Props = {
  title: string;
  description?: string;
  actions?: React.ReactNode;
};

export default function PageHeader({ title, description, actions }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 16,
        padding: 20,
        border: '1px solid #e5e7eb',
        borderRadius: 16,
        background: '#ffffff',
        boxShadow: '0 4px 14px rgba(15,23,42,0.04)',
      }}
    >
      <div>
        <div style={{ fontSize: 28, fontWeight: 800, color: '#0f172a' }}>{title}</div>
        {description ? <div style={{ marginTop: 8, color: '#64748b', fontSize: 14 }}>{description}</div> : null}
      </div>
      {actions ? <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>{actions}</div> : null}
    </div>
  );
}
