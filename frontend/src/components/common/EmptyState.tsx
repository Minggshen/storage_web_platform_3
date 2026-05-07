export function EmptyState(props: { title: string; description?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <div className="text-sm font-medium text-slate-700">{props.title}</div>
      {props.description ? <div className="mt-2 text-sm text-slate-500">{props.description}</div> : null}
    </div>
  );
}
