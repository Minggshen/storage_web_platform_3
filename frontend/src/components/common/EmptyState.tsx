export function EmptyState(props: { title: string; description?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-8 text-center">
      <div className="text-sm font-medium text-foreground">{props.title}</div>
      {props.description ? <div className="mt-2 text-sm text-muted-foreground">{props.description}</div> : null}
    </div>
  );
}
