export function MetricGrid(props: { items: Array<{ label: string; value: number | string | null | undefined; unit?: string }> }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {props.items.map((item) => (
        <div key={item.label} className="rounded-2xl border border-border bg-card p-4 shadow-sm">
          <div className="text-xs text-muted-foreground">{item.label}</div>
          <div className="mt-2 text-xl font-semibold text-foreground">
            {item.value === null || item.value === undefined ? '--' : item.value}
            {item.unit ? <span className="ml-1 text-sm font-normal text-muted-foreground">{item.unit}</span> : null}
          </div>
        </div>
      ))}
    </div>
  );
}
