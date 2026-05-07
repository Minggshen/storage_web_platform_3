import React from 'react';
import type { EdgeType, LineDraft, TopologyEdge, TopologyNode } from './types';

type Props = {
  nodes: TopologyNode[];
  selectedNode: TopologyNode | null;
  selectedEdge: TopologyEdge | null;
  lineDraft: LineDraft;
  onChangeNode: (node: TopologyNode) => void;
  onChangeEdge: (edge: TopologyEdge) => void;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
  onChangeLineDraft: (patch: Partial<LineDraft>) => void;
  onCreateLine: () => void;
};

function parseJson(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function updateParam(node: TopologyNode, key: string, value: unknown): TopologyNode {
  return { ...node, params: { ...node.params, [key]: value } };
}

function updateEdgeParam(edge: TopologyEdge, key: string, value: unknown): TopologyEdge {
  return { ...edge, params: { ...edge.params, [key]: value } };
}

function numberValue(value: unknown, fallback = 0) {
  return typeof value === 'number' ? value : Number(value ?? fallback) || fallback;
}

function stringValue(value: unknown, fallback = '') {
  return typeof value === 'string' ? value : String(value ?? fallback);
}

function booleanValue(value: unknown, fallback = false) {
  return typeof value === 'boolean' ? value : fallback;
}

export function TopologyInspector(props: Props) {
  const {
    nodes,
    selectedNode,
    selectedEdge,
    lineDraft,
    onChangeNode,
    onChangeEdge,
    onDeleteNode,
    onDeleteEdge,
    onChangeLineDraft,
    onCreateLine,
  } = props;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={cardStyle}>
        <h3 style={titleStyle}>线路创建</h3>
        <Field label="起点">
          <select value={lineDraft.from_node_id} onChange={(e) => onChangeLineDraft({ from_node_id: e.target.value })} style={inputStyle}>
            <option value="">请选择</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>{node.name}</option>
            ))}
          </select>
        </Field>
        <Field label="终点">
          <select value={lineDraft.to_node_id} onChange={(e) => onChangeLineDraft({ to_node_id: e.target.value })} style={inputStyle}>
            <option value="">请选择</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>{node.name}</option>
            ))}
          </select>
        </Field>
        <Field label="线路类型">
          <select value={lineDraft.type} onChange={(e) => onChangeLineDraft({ type: e.target.value as EdgeType })} style={inputStyle}>
            <option value="line">普通线路</option>
            <option value="special_line">专线</option>
          </select>
        </Field>
        <button style={primaryBtnStyle} onClick={onCreateLine}>新建线路</button>
      </div>

      {selectedNode ? (
        <div style={cardStyle}>
          <h3 style={titleStyle}>节点属性：{selectedNode.id}</h3>
          <Field label="名称">
            <input value={selectedNode.name} onChange={(e) => onChangeNode({ ...selectedNode, name: e.target.value })} style={inputStyle} />
          </Field>
          <Field label="类型">
            <input value={selectedNode.type} style={inputStyle} disabled />
          </Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Field label="X">
              <input value={selectedNode.position.x} type="number" onChange={(e) => onChangeNode({ ...selectedNode, position: { ...selectedNode.position, x: Number(e.target.value) } })} style={inputStyle} />
            </Field>
            <Field label="Y">
              <input value={selectedNode.position.y} type="number" onChange={(e) => onChangeNode({ ...selectedNode, position: { ...selectedNode.position, y: Number(e.target.value) } })} style={inputStyle} />
            </Field>
          </div>

          {selectedNode.type === 'transformer' ? (
            <>
              <Field label="额定容量 kVA">
                <input type="number" value={numberValue(selectedNode.params.rated_kva, 31500)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'rated_kva', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="基准电压 kV">
                <input type="number" value={numberValue(selectedNode.params.voltage_level_kv, 10)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'voltage_level_kv', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="预留比例">
                <input type="number" step="0.01" value={numberValue(selectedNode.params.reserve_ratio, 0.15)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'reserve_ratio', Number(e.target.value)))} style={inputStyle} />
              </Field>
            </>
          ) : null}

          {selectedNode.type === 'bus' ? (
            <>
              <Field label="基准电压 kV">
                <input type="number" value={numberValue(selectedNode.params.voltage_level_kv, 10)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'voltage_level_kv', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="母线角色">
                <input value={stringValue(selectedNode.params.bus_role, 'feeder')} onChange={(e) => onChangeNode(updateParam(selectedNode, 'bus_role', e.target.value))} style={inputStyle} />
              </Field>
            </>
          ) : null}

          {selectedNode.type === 'ring_main_unit' ? (
            <>
              <Field label="基准电压 kV">
                <input type="number" value={numberValue(selectedNode.params.voltage_level_kv, 10)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'voltage_level_kv', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="出线回路数">
                <input type="number" value={numberValue(selectedNode.params.outlet_count, 4)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'outlet_count', Number(e.target.value)))} style={inputStyle} />
              </Field>
            </>
          ) : null}

          {selectedNode.type === 'branch' ? (
            <>
              <Field label="基准电压 kV">
                <input type="number" value={numberValue(selectedNode.params.voltage_level_kv, 10)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'voltage_level_kv', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="支路序号">
                <input type="number" value={numberValue(selectedNode.params.branch_index, 1)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'branch_index', Number(e.target.value)))} style={inputStyle} />
              </Field>
            </>
          ) : null}

          {selectedNode.type === 'load' ? (
            <>
              <Field label="节点编号 node_id">
                <input type="number" value={numberValue(selectedNode.params.node_id, 1)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'node_id', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="负荷类别">
                <select value={stringValue(selectedNode.params.category, 'industrial')} onChange={(e) => onChangeNode(updateParam(selectedNode, 'category', e.target.value))} style={inputStyle}>
                  <option value="industrial">industrial</option>
                  <option value="commercial">commercial</option>
                  <option value="residential">residential</option>
                </select>
              </Field>
              <Field label="功率因数 pf">
                <input type="number" step="0.01" value={numberValue(selectedNode.params.pf, 0.95)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'pf', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="设计负荷 kW">
                <input type="number" value={numberValue(selectedNode.params.design_kw, 800)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'design_kw', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="变压器容量 kVA">
                <input type="number" value={numberValue(selectedNode.params.transformer_capacity_kva, 2000)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'transformer_capacity_kva', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="变压器功率因数上限">
                <input type="number" step="0.01" value={numberValue(selectedNode.params.transformer_pf_limit, 0.95)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'transformer_pf_limit', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="变压器预留比例">
                <input type="number" step="0.01" value={numberValue(selectedNode.params.transformer_reserve_ratio, 0.15)} onChange={(e) => onChangeNode(updateParam(selectedNode, 'transformer_reserve_ratio', Number(e.target.value)))} style={inputStyle} />
              </Field>
              <Field label="参与配储优化">
                <select value={String(booleanValue(selectedNode.params.optimize_storage, true))} onChange={(e) => onChangeNode(updateParam(selectedNode, 'optimize_storage', e.target.value === 'true'))} style={inputStyle}>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </Field>
            </>
          ) : null}

          <Field label="params JSON">
            <textarea
              value={JSON.stringify(selectedNode.params, null, 2)}
              onChange={(e) => {
                const parsed = parseJson(e.target.value);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                  onChangeNode({ ...selectedNode, params: parsed as Record<string, unknown> });
                }
              }}
              style={textAreaStyle}
            />
          </Field>

          <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
            <button style={primaryBtnStyle} onClick={() => onChangeNode({ ...selectedNode })}>应用 params</button>
            <button style={dangerBtnStyle} onClick={() => onDeleteNode(selectedNode.id)}>删除节点</button>
          </div>
        </div>
      ) : null}

      {selectedEdge ? (
        <div style={cardStyle}>
          <h3 style={titleStyle}>线路属性：{selectedEdge.id}</h3>
          <Field label="名称">
            <input value={selectedEdge.name} onChange={(e) => onChangeEdge({ ...selectedEdge, name: e.target.value })} style={inputStyle} />
          </Field>
          <Field label="类型">
            <select value={selectedEdge.type} onChange={(e) => onChangeEdge({ ...selectedEdge, type: e.target.value as EdgeType })} style={inputStyle}>
              <option value="line">普通线路</option>
              <option value="special_line">专线</option>
            </select>
          </Field>
          <Field label="起点">
            <input value={selectedEdge.from_node_id} style={inputStyle} disabled />
          </Field>
          <Field label="终点">
            <input value={selectedEdge.to_node_id} style={inputStyle} disabled />
          </Field>
          <Field label="长度 km">
            <input type="number" step="0.01" value={numberValue(selectedEdge.params.length_km, 0.6)} onChange={(e) => onChangeEdge(updateEdgeParam(selectedEdge, 'length_km', Number(e.target.value)))} style={inputStyle} />
          </Field>
          <Field label="R Ω/km">
            <input type="number" step="0.001" value={numberValue(selectedEdge.params.r_ohm_per_km, 0.38)} onChange={(e) => onChangeEdge(updateEdgeParam(selectedEdge, 'r_ohm_per_km', Number(e.target.value)))} style={inputStyle} />
          </Field>
          <Field label="X Ω/km">
            <input type="number" step="0.001" value={numberValue(selectedEdge.params.x_ohm_per_km, 0.12)} onChange={(e) => onChangeEdge(updateEdgeParam(selectedEdge, 'x_ohm_per_km', Number(e.target.value)))} style={inputStyle} />
          </Field>
          <Field label="额定电流 A">
            <input type="number" value={numberValue(selectedEdge.params.rated_current_a, selectedEdge.type === 'special_line' ? 400 : 250)} onChange={(e) => onChangeEdge(updateEdgeParam(selectedEdge, 'rated_current_a', Number(e.target.value)))} style={inputStyle} />
          </Field>
          <Field label="基准电压 kV">
            <input type="number" value={numberValue(selectedEdge.params.voltage_level_kv, 10)} onChange={(e) => onChangeEdge(updateEdgeParam(selectedEdge, 'voltage_level_kv', Number(e.target.value)))} style={inputStyle} />
          </Field>
          <Field label="params JSON">
            <textarea
              value={JSON.stringify(selectedEdge.params, null, 2)}
              onChange={(e) => {
                const parsed = parseJson(e.target.value);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                  onChangeEdge({ ...selectedEdge, params: parsed as Record<string, unknown> });
                }
              }}
              style={textAreaStyle}
            />
          </Field>
          <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
            <button style={primaryBtnStyle} onClick={() => onChangeEdge({ ...selectedEdge })}>应用 params</button>
            <button style={dangerBtnStyle} onClick={() => onDeleteEdge(selectedEdge.id)}>删除线路</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ color: '#64748b', fontSize: 12, marginBottom: 6 }}>{props.label}</div>
      {props.children}
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 18,
  padding: 14,
};

const titleStyle: React.CSSProperties = {
  margin: '0 0 12px 0',
  fontSize: 18,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 10,
  padding: '10px 12px',
  background: '#ffffff',
};

const textAreaStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 110,
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 10,
  padding: '10px 12px',
  fontFamily: 'Consolas, Menlo, Monaco, monospace',
  fontSize: 12,
  resize: 'vertical',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 12,
  border: '1px solid #111827',
  background: '#111827',
  color: '#ffffff',
  fontWeight: 700,
  cursor: 'pointer',
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 12,
  border: '1px solid #fca5a5',
  background: '#ffffff',
  color: '#dc2626',
  fontWeight: 700,
  cursor: 'pointer',
};

export default TopologyInspector;
