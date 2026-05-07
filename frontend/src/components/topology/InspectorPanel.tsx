import type { TopologyNodeRecord } from "../../types/api";

export function InspectorPanel(props: {
  node?: TopologyNodeRecord;
  onChange: (patch: Partial<TopologyNodeRecord>) => void;
}) {
  if (!props.node) {
    return <div className="rounded-2xl border bg-white p-4 text-sm text-slate-500">请选择一个节点。</div>;
  }

  const node = props.node;

  return (
    <div className="space-y-4 rounded-2xl border bg-white p-4">
      <div className="text-sm font-semibold">节点属性</div>
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">节点名称</span>
        <input className="w-full rounded-xl border px-3 py-2" value={node.name} onChange={(e) => props.onChange({ name: e.target.value })} />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">基准电压 kV</span>
        <input className="w-full rounded-xl border px-3 py-2" type="number" value={node.voltageLevelKv ?? ""} onChange={(e) => props.onChange({ voltageLevelKv: Number(e.target.value) || undefined })} />
      </label>
      {node.type === "load" ? (
        <>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">变压器容量 kVA</span>
            <input className="w-full rounded-xl border px-3 py-2" type="number" value={node.transformerCapacityKva ?? ""} onChange={(e) => props.onChange({ transformerCapacityKva: Number(e.target.value) || null })} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">功率因数上限</span>
            <input className="w-full rounded-xl border px-3 py-2" type="number" step="0.01" value={node.transformerPfLimit ?? ""} onChange={(e) => props.onChange({ transformerPfLimit: Number(e.target.value) || null })} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">保留裕度</span>
            <input className="w-full rounded-xl border px-3 py-2" type="number" step="0.01" value={node.transformerReserveRatio ?? ""} onChange={(e) => props.onChange({ transformerReserveRatio: Number(e.target.value) || null })} />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">无功/有功比</span>
            <input className="w-full rounded-xl border px-3 py-2" type="number" step="0.01" value={node.qToPRatio ?? ""} onChange={(e) => props.onChange({ qToPRatio: Number(e.target.value) || null })} />
          </label>
        </>
      ) : null}
    </div>
  );
}
