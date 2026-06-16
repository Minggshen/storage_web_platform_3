import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { TopologyEdge, TopologyNode } from './types';
import { LINE_STROKE_BY_CODE } from '../../pages/workspace/topologyConstants';

type Props = {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string | null) => void;
  onMoveNode: (id: string, x: number, y: number) => void;
};

type DragState = {
  nodeId: string;
  offsetX: number;
  offsetY: number;
} | null;

const NODE_WIDTH = 166;
const NODE_HEIGHT = 76;
const PADDING = 160;
const GRID_MINOR = 24;
const GRID_MAJOR = 120;

function nodeColor(type: string) {
  switch (type) {
    case 'transformer':
      return '#f59e0b';
    case 'bus':
      return '#2563eb';
    case 'ring_main_unit':
      return '#6b7280';
    case 'branch':
      return '#0f766e';
    case 'load':
      return '#16a34a';
    default:
      return '#111827';
  }
}

const NODE_TYPE_CN: Record<string, string> = {
  transformer: '主变',
  bus: '母线',
  ring_main_unit: '环网柜',
  branch: '分支点',
  load: '负荷',
};

const LINECODE_CN: Record<string, string> = {
  LC_MAIN: '主干线',
  LC_BRANCH: '分支线',
  LC_CABLE: '电缆',
  LC_LIGHT: '轻载线',
};

/* ---- 各元件 SVG 图标（24×24 viewBox） ---- */

function TransformerIcon({ color }: { color: string }) {
  return (
    <svg width="32" height="28" viewBox="0 0 32 28" fill="none" aria-hidden="true">
      <circle cx="10" cy="14" r="8" stroke={color} strokeWidth="2" fill="#fffbeb" />
      <circle cx="22" cy="14" r="8" stroke={color} strokeWidth="2" fill="#fffbeb" />
      <line x1="18" y1="11" x2="18" y2="17" stroke={color} strokeWidth="1.8" />
      <line x1="14" y1="11" x2="14" y2="17" stroke={color} strokeWidth="1.8" />
      <line x1="18" y1="14" x2="14" y2="14" stroke={color} strokeWidth="1.2" />
    </svg>
  );
}

function BusIcon({ color }: { color: string }) {
  return (
    <svg width="32" height="28" viewBox="0 0 32 28" fill="none" aria-hidden="true">
      <rect x="2" y="6" width="28" height="5" rx="2.5" fill={color} opacity="0.15" />
      <rect x="2" y="6" width="28" height="5" rx="2.5" stroke={color} strokeWidth="1.8" fill="none" />
      <line x1="8" y1="11" x2="8" y2="22" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="16" y1="11" x2="16" y2="22" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <line x1="24" y1="11" x2="24" y2="22" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function RingMainUnitIcon({ color }: { color: string }) {
  return (
    <svg width="32" height="28" viewBox="0 0 32 28" fill="none" aria-hidden="true">
      <rect x="4" y="3" width="24" height="22" rx="4" stroke={color} strokeWidth="1.8" fill="#f9fafb" />
      <line x1="4" y1="13" x2="28" y2="13" stroke={color} strokeWidth="1.2" opacity="0.5" />
      <circle cx="8" cy="8" r="2" fill={color} />
      <circle cx="16" cy="8" r="2" fill={color} />
      <circle cx="24" cy="8" r="2" fill={color} />
      <circle cx="16" cy="20" r="2" fill={color} opacity="0.5" />
    </svg>
  );
}

function BranchIcon({ color }: { color: string }) {
  return (
    <svg width="32" height="28" viewBox="0 0 32 28" fill="none" aria-hidden="true">
      <line x1="16" y1="2" x2="16" y2="26" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <line x1="16" y1="14" x2="28" y2="14" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="16" cy="14" r="4" fill={color} opacity="0.2" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

function LoadIcon({ color }: { color: string }) {
  return (
    <svg width="32" height="28" viewBox="0 0 32 28" fill="none" aria-hidden="true">
      <path d="M6 26V12L16 2L26 12V26H6Z" stroke={color} strokeWidth="1.8" fill={color} opacity="0.12" />
      <rect x="12" y="16" width="8" height="10" rx="1" fill={color} opacity="0.3" stroke={color} strokeWidth="1.2" />
      <line x1="11" y1="22" x2="21" y2="22" stroke={color} strokeWidth="1.2" opacity="0.6" />
    </svg>
  );
}

function nodeIcon(type: string, color: string) {
  switch (type) {
    case 'transformer':
      return <TransformerIcon color={color} />;
    case 'bus':
      return <BusIcon color={color} />;
    case 'ring_main_unit':
      return <RingMainUnitIcon color={color} />;
    case 'branch':
      return <BranchIcon color={color} />;
    case 'load':
      return <LoadIcon color={color} />;
    default:
      return <BranchIcon color={color} />;
  }
}

function nodeParamsSummary(type: string, params: Record<string, unknown>): string {
  switch (type) {
    case 'transformer': {
      const kva = params.rated_kva;
      const hv = params.primary_voltage_kv;
      const lv = params.voltage_level_kv;
      if (kva && hv && lv) return `${kva} kVA · ${hv}/${lv} kV`;
      if (kva) return `${kva} kVA`;
      return '';
    }
    case 'bus': {
      const kv = params.voltage_level_kv;
      const role = params.bus_role;
      const parts = [kv ? `${kv} kV` : '', role && role !== 'feeder' ? String(role) : ''].filter(Boolean);
      return parts.join(' · ');
    }
    case 'ring_main_unit': {
      const kv = params.voltage_level_kv;
      const outlets = params.outlet_count;
      const parts = [kv ? `${kv} kV` : '', outlets ? `${outlets}回路` : ''].filter(Boolean);
      return parts.join(' · ');
    }
    case 'branch': {
      const kv = params.voltage_level_kv;
      return kv ? `${kv} kV` : '';
    }
    case 'load': {
      const kw = params.design_kw;
      const cat = params.category;
      const catLabel = typeof cat === 'string' ? (cat === 'industrial' ? '工业' : cat === 'commercial' ? '商业' : cat === 'residential' ? '居民' : '') : '';
      const parts = [kw ? `${kw} kW` : '', catLabel].filter(Boolean);
      return parts.join(' · ');
    }
    default:
      return '';
  }
}

export function TopologyCanvas(props: Props) {
  const { nodes, edges, selectedNodeId, selectedEdgeId, onSelectNode, onSelectEdge, onMoveNode } = props;
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<DragState>(null);

  const stageSize = useMemo(() => {
    const maxX = Math.max(0, ...nodes.map((n) => n.position.x));
    const maxY = Math.max(0, ...nodes.map((n) => n.position.y));
    return {
      width: Math.max(1400, maxX + NODE_WIDTH + PADDING),
      height: Math.max(860, maxY + NODE_HEIGHT + PADDING),
    };
  }, [nodes]);

  useEffect(() => {
    function onWindowMove(event: MouseEvent) {
      if (!drag || !stageRef.current || !viewportRef.current) return;
      const stageRect = stageRef.current.getBoundingClientRect();
      const viewport = viewportRef.current;
      const x = event.clientX - stageRect.left + viewport.scrollLeft - drag.offsetX;
      const y = event.clientY - stageRect.top + viewport.scrollTop - drag.offsetY;
      const boundedX = Math.max(20, Math.min(stageSize.width - NODE_WIDTH - 20, x));
      const boundedY = Math.max(20, Math.min(stageSize.height - NODE_HEIGHT - 20, y));
      onMoveNode(drag.nodeId, Math.round(boundedX), Math.round(boundedY));
    }

    function onWindowUp() {
      setDrag(null);
    }

    window.addEventListener('mousemove', onWindowMove);
    window.addEventListener('mouseup', onWindowUp);
    return () => {
      window.removeEventListener('mousemove', onWindowMove);
      window.removeEventListener('mouseup', onWindowUp);
    };
  }, [drag, onMoveNode, stageSize.height, stageSize.width]);

  const nodeMap = useMemo(() => Object.fromEntries(nodes.map((node) => [node.id, node])), [nodes]);

  return (
    <div style={cardStyle}>
      <div style={cardHeaderStyle}>
        <strong>可视化画布</strong>
        <span style={{ color: '#64748b', fontSize: 12 }}>支持拖拽、选中和线路预览</span>
      </div>

      <div ref={viewportRef} style={viewportStyle} onMouseDown={() => { onSelectNode(null); onSelectEdge(null); }}>
        <div ref={stageRef} style={{ ...stageStyle, width: stageSize.width, height: stageSize.height }}>
          <svg width={stageSize.width} height={stageSize.height} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
            {renderGrid(stageSize.width, stageSize.height)}
            {edges.map((edge) => {
              const fromNode = nodeMap[edge.from_node_id];
              const toNode = nodeMap[edge.to_node_id];
              if (!fromNode || !toNode) return null;
              const x1 = fromNode.position.x + NODE_WIDTH / 2;
              const y1 = fromNode.position.y + NODE_HEIGHT / 2;
              const x2 = toNode.position.x + NODE_WIDTH / 2;
              const y2 = toNode.position.y + NODE_HEIGHT / 2;
              const selected = selectedEdgeId === edge.id;
              const linecode = typeof edge.params.linecode === 'string' ? edge.params.linecode : '';
              const linecodeLabel = LINECODE_CN[linecode] || linecode || '';
              const lengthKm = typeof edge.params.length_km === 'number' ? `${edge.params.length_km}km` : '';
              const label = [edge.name, lengthKm, linecodeLabel].filter(Boolean).join(' · ');
              const lineStroke = selected ? '#ef4444' : (LINE_STROKE_BY_CODE[linecode] || '#64748b');
              const isDashed = edge.type !== 'special_line';
              return (
                <g key={edge.id} onMouseDown={(event) => { event.stopPropagation(); onSelectEdge(edge.id); onSelectNode(null); }} style={{ cursor: 'pointer' }}>
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke={lineStroke}
                    strokeDasharray={isDashed ? '8 5' : undefined}
                    strokeWidth={selected ? 3.5 : 2.75}
                    strokeLinecap="round"
                  />
                  <text
                    x={(x1 + x2) / 2}
                    y={(y1 + y2) / 2 - 6}
                    fill="#475569"
                    fontSize="11"
                    textAnchor="middle"
                    style={{ userSelect: 'none', pointerEvents: 'none', paintOrder: 'stroke', stroke: '#ffffff', strokeWidth: 3 }}
                  >
                    {label}
                  </text>
                </g>
              );
            })}
          </svg>

          {nodes.map((node) => {
            const selected = selectedNodeId === node.id;
            const color = nodeColor(node.type);
            const typeLabel = NODE_TYPE_CN[node.type] || node.type;
            const paramText = nodeParamsSummary(node.type, node.params);
            return (
              <div
                key={node.id}
                onMouseDown={(event) => {
                  event.stopPropagation();
                  const rect = (event.currentTarget as HTMLDivElement).getBoundingClientRect();
                  setDrag({
                    nodeId: node.id,
                    offsetX: event.clientX - rect.left,
                    offsetY: event.clientY - rect.top,
                  });
                  onSelectNode(node.id);
                  onSelectEdge(null);
                }}
                style={{
                  ...nodeStyle,
                  left: node.position.x,
                  top: node.position.y,
                  borderColor: selected ? '#ef4444' : '#cbd5e1',
                  boxShadow: selected ? `0 0 0 2.5px rgba(239,68,68,0.18)` : `0 6px 18px rgba(15,23,42,0.06)`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  {nodeIcon(node.type, color)}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <strong style={{ fontSize: 13, color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {node.name}
                      </strong>
                      <span style={{
                        fontSize: 10,
                        color,
                        background: `${color}15`,
                        padding: '1px 6px',
                        borderRadius: 4,
                        whiteSpace: 'nowrap',
                        flex: '0 0 auto',
                      }}>
                        {typeLabel}
                      </span>
                    </div>
                    {paramText && (
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {paramText}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function renderGrid(width: number, height: number) {
  const lines: React.ReactNode[] = [];
  for (let x = 0; x <= width; x += GRID_MINOR) {
    const major = x % GRID_MAJOR === 0;
    lines.push(
      <line
        key={`vx-${x}`}
        x1={x}
        y1={0}
        x2={x}
        y2={height}
        stroke={major ? '#d7e3f4' : '#edf2f7'}
        strokeWidth={major ? 1.1 : 0.8}
      />,
    );
  }
  for (let y = 0; y <= height; y += GRID_MINOR) {
    const major = y % GRID_MAJOR === 0;
    lines.push(
      <line
        key={`hy-${y}`}
        x1={0}
        y1={y}
        x2={width}
        y2={y}
        stroke={major ? '#d7e3f4' : '#edf2f7'}
        strokeWidth={major ? 1.1 : 0.8}
      />,
    );
  }
  return <g>{lines}</g>;
}

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 18,
  padding: 16,
  overflow: 'hidden',
};

const cardHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  marginBottom: 12,
};

const viewportStyle: React.CSSProperties = {
  width: '100%',
  height: 760,
  overflow: 'auto',
  borderRadius: 14,
  border: '1px solid #dbe3ef',
  background: '#f8fbff',
};

const stageStyle: React.CSSProperties = {
  position: 'relative',
  background: 'linear-gradient(180deg, rgba(255,255,255,0.85), rgba(248,250,252,0.92))',
};

const nodeStyle: React.CSSProperties = {
  position: 'absolute',
  width: NODE_WIDTH,
  minHeight: NODE_HEIGHT,
  padding: '10px 12px',
  borderRadius: 12,
  background: '#ffffff',
  border: '1.5px solid #cbd5e1',
  boxSizing: 'border-box',
  cursor: 'grab',
  userSelect: 'none',
};

export default TopologyCanvas;
