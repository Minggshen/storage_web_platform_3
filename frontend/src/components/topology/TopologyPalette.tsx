import React from 'react';
import type { NodeType } from './types';

type Props = {
  onAddNode: (type: NodeType) => void;
};

const paletteItems: Array<{ type: NodeType; label: string; icon: string }> = [
  { type: 'transformer', label: '主变', icon: '⚡' },
  { type: 'bus', label: '母线', icon: '▣' },
  { type: 'ring_main_unit', label: '环网柜', icon: '⌗' },
  { type: 'branch', label: '分支点', icon: '◉' },
  { type: 'load', label: '负荷', icon: '🗂' },
];

export function TopologyPalette({ onAddNode }: Props) {
  return (
    <div style={cardStyle}>
      <h3 style={{ margin: '0 0 12px 0', fontSize: 18 }}>元件面板</h3>
      <div style={{ display: 'grid', gap: 10 }}>
        {paletteItems.map((item) => (
          <button key={item.type} onClick={() => onAddNode(item.type)} style={itemStyle}>
            <span style={{ fontSize: 16 }}>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 12, lineHeight: 1.5 }}>
        先添加节点，再在右侧“线路创建”里选择起点和终点。
      </div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 18,
  padding: 14,
};

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  padding: '10px 12px',
  borderRadius: 12,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  cursor: 'pointer',
  fontWeight: 600,
  color: '#111827',
  textAlign: 'left',
};

export default TopologyPalette;
