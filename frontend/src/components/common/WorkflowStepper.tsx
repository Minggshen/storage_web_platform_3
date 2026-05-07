import { StatusBadge } from './StatusBadge';

export function WorkflowStepper(props: { steps: Array<{ key: string; label: string; status: string; detail?: string | null }> }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {props.steps.map((step, index) => (
          <div key={step.key} className="rounded-2xl border border-slate-200 p-4">
            <div className="mb-2 text-xs text-slate-400">步骤 {index + 1}</div>
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-medium text-slate-900">{step.label}</div>
              <StatusBadge value={step.status} />
            </div>
            {step.detail ? <div className="mt-2 text-xs text-slate-500">{step.detail}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
