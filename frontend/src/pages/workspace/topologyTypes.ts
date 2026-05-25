export type NodeKind =
  | 'grid'
  | 'transformer'
  | 'distribution_transformer'
  | 'bus'
  | 'ring_main_unit'
  | 'branch'
  | 'switch'
  | 'breaker'
  | 'fuse'
  | 'regulator'
  | 'capacitor'
  | 'pv'
  | 'wind'
  | 'storage'
  | 'load';

export type EdgeKind = 'line' | 'normal_line' | 'special_line';

export type Position = {
  x: number;
  y: number;
};

export type TopologyNode = {
  id: string;
  type: string;
  name?: string;
  position?: Position;
  params?: Record<string, unknown>;
  runtime_binding?: unknown;
  tags?: string[];
};

export type TopologyEdge = {
  id: string;
  type: string;
  name?: string;
  from_node_id: string;
  to_node_id: string;
  params?: Record<string, unknown>;
};

export type TopologyData = {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  economic_parameters: Record<string, unknown>;
};

export type TopologyDraft = Omit<TopologyData, 'economic_parameters'> & {
  economic_parameters?: Record<string, unknown>;
};

export type Selection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | null;

export type NodeVisualSpec = {
  color: string;
  border: string;
  background: string;
  radius: number | string;
  width: number;
  height: number;
  clipPath?: string;
};

export type LoadCategory = 'industrial' | 'commercial' | 'residential';

export type DistributionServiceEdgeProfile = {
  linecode: string;
  defaultLengthKm: number;
  secondaryKv: number;
  transformerKva: number;
  resourceKva: number;
  transformerCurrentA: number;
  resourceCurrentA: number;
  ratedCurrentA: number;
  emergCurrentA: number;
};
