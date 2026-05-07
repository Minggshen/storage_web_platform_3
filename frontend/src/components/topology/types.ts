export type NodeType = 'transformer' | 'bus' | 'ring_main_unit' | 'branch' | 'load';
export type EdgeType = 'line' | 'special_line';

export type NodePosition = {
  x: number;
  y: number;
};

export type GenericParams = Record<string, unknown>;

export type TransformerParams = {
  rated_kva: number;
  voltage_level_kv: number;
  reserve_ratio?: number;
};

export type BusParams = {
  voltage_level_kv: number;
  bus_role?: string;
};

export type RingMainUnitParams = {
  voltage_level_kv: number;
  outlet_count?: number;
};

export type BranchParams = {
  voltage_level_kv?: number;
  branch_index?: number;
};

export type LoadParams = {
  node_id?: number;
  category?: string;
  pf?: number;
  optimize_storage?: boolean;
  transformer_capacity_kva?: number;
  transformer_pf_limit?: number;
  transformer_reserve_ratio?: number;
  design_kw?: number;
  voltage_level_kv?: number;
};

export type LineParams = {
  length_km: number;
  linecode?: 'LC_MAIN' | 'LC_BRANCH' | 'LC_CABLE' | 'LC_LIGHT';
  r_ohm_per_km: number;
  x_ohm_per_km: number;
  rated_current_a?: number;
  emerg_current_a?: number;
  voltage_level_kv?: number;
  phases?: 1 | 3;
  enabled?: boolean;
  normally_open?: boolean;
};

export type TopologyNode = {
  id: string;
  type: NodeType;
  name: string;
  position: NodePosition;
  params: GenericParams;
  runtime_binding?: unknown;
  tags?: string[];
};

export type TopologyEdge = {
  id: string;
  type: EdgeType;
  name: string;
  from_node_id: string;
  to_node_id: string;
  params: GenericParams;
};

export type TopologyModel = {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
};

export type LineDraft = {
  from_node_id: string;
  to_node_id: string;
  type: EdgeType;
};

const DEFAULT_NODE_NAMES: Record<NodeType, string> = {
  transformer: '主变',
  bus: '母线',
  ring_main_unit: '环网柜',
  branch: '分支点',
  load: '负荷',
};

export function createDefaultNode(type: NodeType, index: number): TopologyNode {
  const name = `${DEFAULT_NODE_NAMES[type]}${index}`;
  const basePosition = { x: 120 + (index % 4) * 180, y: 120 + Math.floor(index / 4) * 140 };

  const defaultParams: Record<NodeType, GenericParams> = {
    transformer: {
      rated_kva: 31500,
      voltage_level_kv: 10,
      primary_voltage_kv: 110,
      primary_bus_name: 'sourcebus',
      dss_bus_name: 'n0',
      phases: 3,
      reserve_ratio: 0.15,
    },
    bus: {
      voltage_level_kv: 10,
      dss_bus_name: '',
      phases: 3,
      bus_role: 'feeder',
    },
    ring_main_unit: {
      voltage_level_kv: 10,
      outlet_count: 4,
    },
    branch: {
      voltage_level_kv: 10,
      dss_bus_name: '',
      phases: 3,
      branch_index: index,
    },
    load: {
      node_id: index,
      dss_bus_name: '',
      dss_load_name: '',
      target_kv_ln: null,
      phases: 3,
      category: 'industrial',
      pf: 0.95,
      optimize_storage: true,
      transformer_capacity_kva: 2000,
      transformer_pf_limit: 0.95,
      transformer_reserve_ratio: 0.15,
      design_kw: 800,
      voltage_level_kv: 10,
    },
  } as unknown as Record<NodeType, GenericParams>;

  return {
    id: `${type}_${String(index).padStart(3, '0')}`,
    type,
    name,
    position: basePosition,
    params: defaultParams[type],
    runtime_binding: null,
    tags: [],
  };
}

export function createDefaultEdge(index: number, fromNodeId: string, toNodeId: string, type: EdgeType): TopologyEdge {
  return {
    id: `line_${String(index).padStart(3, '0')}`,
    type,
    name: type === 'special_line' ? `专线${index}` : `线路${index}`,
    from_node_id: fromNodeId,
    to_node_id: toNodeId,
    params: {
      length_km: 0.6,
      linecode: type === 'special_line' ? 'LC_CABLE' : 'LC_MAIN',
      r_ohm_per_km: type === 'special_line' ? 0.254261364 : 0.251742424,
      x_ohm_per_km: type === 'special_line' ? 0.097045455 : 0.255208333,
      rated_current_a: type === 'special_line' ? 1400 : 1200,
      emerg_current_a: type === 'special_line' ? 1700 : 1500,
      voltage_level_kv: 10,
      phases: 3,
      enabled: true,
      normally_open: false,
    },
  };
}
