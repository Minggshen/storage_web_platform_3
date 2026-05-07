export function MetricGrid(props: { items: Array<{ label: string; value: number | string | null | undefined; unit?: string }> }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {props.items.map((item) => (
        <div key={item.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="text-xs text-slate-500">{item.label}</div>
          <div className="mt-2 text-xl font-semibold text-slate-900">
            {item.value === null || item.value === undefined ? '--' : item.value}
            {item.unit ? <span className="ml-1 text-sm font-normal text-slate-500">{item.unit}</span> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
