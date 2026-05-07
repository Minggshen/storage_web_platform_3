import React from 'react';

type Props = {
  title: string;
  children: React.ReactNode;
  extra?: React.ReactNode;
};

export default function SectionCard({ title, children, extra }: Props) {
  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-xs">
      <div className="mb-3.5 flex items-center justify-between gap-3">
        <h2 className="m-0 text-[22px] font-bold text-foreground">{title}</h2>
        {extra}
      </div>
      {children}
    </section>
  );
}
