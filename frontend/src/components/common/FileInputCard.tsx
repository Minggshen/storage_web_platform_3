import { useRef } from "react";

export function FileInputCard(props: {
  title: string;
  description?: string;
  onSelect: (file: File) => void;
  selectedName?: string | null;
  accept?: string;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div className="rounded-2xl border border-dashed bg-slate-50 p-4">
      <div className="text-sm font-medium">{props.title}</div>
      {props.description ? <div className="mt-1 text-xs text-slate-500">{props.description}</div> : null}
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          className="rounded-xl bg-slate-900 px-3 py-2 text-sm text-white"
          onClick={() => inputRef.current?.click()}
        >
          选择文件
        </button>
        <span className="text-sm text-slate-600">{props.selectedName ?? "未选择文件"}</span>
      </div>
      <input
        ref={inputRef}
        hidden
        type="file"
        accept={props.accept}
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) props.onSelect(file);
        }}
      />
    </div>
  );
}
