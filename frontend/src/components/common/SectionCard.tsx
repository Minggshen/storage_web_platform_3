import React from 'react';

type Props = {
  title: string;
  children: React.ReactNode;
  extra?: React.ReactNode;
};

export default function SectionCard({ title, children, extra }: Props) {
  return (
    <section
      style={{
        background: '#ffffff',
        border: '1px solid #e5e7eb',
        borderRadius: 16,
        padding: 20,
        boxShadow: '0 4px 14px rgba(15,23,42,0.04)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          marginBottom: 14,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 22, color: '#0f172a' }}>{title}</h2>
        {extra}
      </div>
      {children}
    </section>
  );
}
