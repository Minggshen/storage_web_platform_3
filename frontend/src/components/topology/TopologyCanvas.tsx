import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { TopologyEdge, TopologyNode } from './types';

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

const NODE_WIDTH = 132;
const NODE_HEIGHT = 62;
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

function displayType(type: string) {
  if (type === 'ring_main_unit') return 'rmu';
  return type;
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
              return (
                <g key={edge.id} onMouseDown={(event) => { event.stopPropagation(); onSelectEdge(edge.id); onSelectNode(null); }} style={{ cursor: 'pointer' }}>
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke={selected ? '#ef4444' : edge.type === 'special_line' ? '#2563eb' : '#64748b'}
                    strokeDasharray={edge.type === 'special_line' ? undefined : '6 4'}
                    strokeWidth={selected ? 3 : 2.25}
                  />
                  <text
                    x={(x1 + x2) / 2}
                    y={(y1 + y2) / 2 - 6}
                    fill="#64748b"
                    fontSize="11"
                    textAnchor="middle"
                    style={{ userSelect: 'none', pointerEvents: 'none' }}
                  >
                    {edge.name}
                  </text>
                </g>
              );
            })}
          </svg>

          {nodes.map((node) => {
            const selected = selectedNodeId === node.id;
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
                  boxShadow: selected ? '0 0 0 2px rgba(239,68,68,0.15)' : '0 6px 18px rgba(15,23,42,0.06)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: nodeColor(node.type), flex: '0 0 auto' }} />
                  <strong style={{ fontSize: 13, color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {node.name}
                  </strong>
                </div>
                <div style={{ fontSize: 12, color: '#64748b' }}>{displayType(node.type)}</div>
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
