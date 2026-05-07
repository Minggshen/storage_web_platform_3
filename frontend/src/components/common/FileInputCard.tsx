import { useRef } from "react";
import { Button } from "@/components/ui/button";

export function FileInputCard(props: {
  title: string;
  description?: string;
  onSelect: (file: File) => void;
  selectedName?: string | null;
  accept?: string;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-4">
      <div className="text-sm font-medium text-foreground">{props.title}</div>
      {props.description ? <div className="mt-1 text-xs text-muted-foreground">{props.description}</div> : null}
      <div className="mt-3 flex items-center gap-3">
        <Button
          type="button"
          size="sm"
          onClick={() => inputRef.current?.click()}
        >
          选择文件
        </Button>
        <span className="text-sm text-muted-foreground">{props.selectedName ?? "未选择文件"}</span>
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
