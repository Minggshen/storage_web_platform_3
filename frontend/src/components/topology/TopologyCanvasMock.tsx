import type { TopologyEdgeRecord, TopologyNodeRecord } from "../../types/api";

export function TopologyCanvasMock(props: {
  nodes: TopologyNodeRecord[];
  edges: TopologyEdgeRecord[];
  selectedNodeId?: string;
  onSelectNode: (nodeId: string) => void;
}) {
  return (
    <div className="rounded-2xl border bg-white p-4">
      <div className="mb-3 text-sm font-medium">拓扑画布（骨架版）</div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {props.nodes.map((node) => {
          const selected = props.selectedNodeId === node.id;
          return (
            <button
              key={node.id}
              type="button"
              onClick={() => props.onSelectNode(node.id)}
              className={`rounded-2xl border p-4 text-left ${selected ? "border-slate-900 bg-slate-100" : "border-slate-200"}`}
            >
              <div className="text-xs text-slate-500">{node.type}</div>
              <div className="mt-1 font-medium">{node.name}</div>
              <div className="mt-2 text-xs text-slate-500">节点ID：{node.id}</div>
            </button>
          );
        })}
      </div>
      <div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
        当前线路数：{props.edges.length}。这一版先把工作流与数据流打通，后续可替换为真正的图编辑器。
      </div>
    </div>
  );
}
