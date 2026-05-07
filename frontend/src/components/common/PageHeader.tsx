import React from 'react';

type Props = {
  title: string;
  description?: string;
  actions?: React.ReactNode;
};

export default function PageHeader({ title, description, actions }: Props) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl border border-border bg-card p-5 shadow-xs">
      <div>
        <h1 className="text-[28px] font-extrabold tracking-tight text-foreground">{title}</h1>
        {description ? <p className="mt-2 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex gap-2.5 flex-wrap">{actions}</div> : null}
    </div>
  );
}
