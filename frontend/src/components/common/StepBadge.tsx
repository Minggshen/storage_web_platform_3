export default function StepBadge({ step, label }: { step: number; label: string }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
        {step}
      </span>
      <span className="text-base font-bold text-foreground">{label}</span>
    </div>
  );
}
