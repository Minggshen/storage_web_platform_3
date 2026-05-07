export function CodeBlock({ text, maxHeight = 360 }: { text: string; maxHeight?: number }) {
  return (
    <pre className="overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-100" style={{ maxHeight }}>
      {text || '暂无内容'}
    </pre>
  );
}
