import type { TopologyEdge, TopologyModel, TopologyNode } from '../components/topology/types';

type MappingWarning = {
  level: 'warning' | 'error';
  message: string;
};

export type OpenDssArtifact = {
  buses: Array<Record<string, unknown>>;
  lines: Array<Record<string, unknown>>;
  loads: Array<Record<string, unknown>>;
  transformers: Array<Record<string, unknown>>;
  warnings: MappingWarning[];
  dssPreview: string;
};

function slug(input: string) {
  return input
    .replace(/[^a-zA-Z0-9_\-\u4e00-\u9fa5]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '') || 'unnamed';
}

function busName(node: TopologyNode) {
  return slug(node.id.toLowerCase());
}

function voltageKv(node: TopologyNode) {
  const value = Number(node.params.voltage_level_kv ?? 10);
  return Number.isFinite(value) && value > 0 ? value : 10;
}

function lineVoltageKv(edge: TopologyEdge, fallback = 10) {
  const value = Number(edge.params.voltage_level_kv ?? fallback);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function lengthKm(edge: TopologyEdge) {
  const value = Number(edge.params.length_km ?? 0.6);
  return Number.isFinite(value) && value > 0 ? value : 0.6;
}

function rPerKm(edge: TopologyEdge) {
  const value = Number(edge.params.r_ohm_per_km ?? 0.38);
  return Number.isFinite(value) ? value : 0.38;
}

function xPerKm(edge: TopologyEdge) {
  const value = Number(edge.params.x_ohm_per_km ?? 0.12);
  return Number.isFinite(value) ? value : 0.12;
}

export function buildOpenDssArtifacts(model: TopologyModel): OpenDssArtifact {
  const nodeMap = new Map(model.nodes.map((node) => [node.id, node]));
  const warnings: MappingWarning[] = [];

  const buses = model.nodes.map((node) => ({
    node_id: node.id,
    node_name: node.name,
    bus_name: busName(node),
    node_type: node.type,
    voltage_level_kv: voltageKv(node),
  }));

  const transformers = model.nodes
    .filter((node) => node.type === 'transformer')
    .map((node) => ({
      node_id: node.id,
      name: node.name,
      dss_name: `XF_${slug(node.id)}`,
      bus_name: busName(node),
      rated_kva: Number(node.params.rated_kva ?? 31500),
      voltage_level_kv: voltageKv(node),
      reserve_ratio: Number(node.params.reserve_ratio ?? 0.15),
    }));

  const loads = model.nodes
    .filter((node) => node.type === 'load')
    .map((node) => ({
      node_id: node.id,
      name: node.name,
      dss_name: `LD_${slug(node.id)}`,
      bus_name: busName(node),
      category: String(node.params.category ?? 'industrial'),
      pf: Number(node.params.pf ?? 0.95),
      design_kw: Number(node.params.design_kw ?? 800),
      transformer_capacity_kva: Number(node.params.transformer_capacity_kva ?? 2000),
      optimize_storage: Boolean(node.params.optimize_storage ?? true),
      voltage_level_kv: voltageKv(node),
    }));

  const lines = model.edges.map((edge) => {
    const fromNode = nodeMap.get(edge.from_node_id);
    const toNode = nodeMap.get(edge.to_node_id);

    if (!fromNode || !toNode) {
      warnings.push({ level: 'error', message: `线路 ${edge.id} 的起止节点不存在。` });
    }

    return {
      edge_id: edge.id,
      name: edge.name,
      dss_name: `LN_${slug(edge.id)}`,
      edge_type: edge.type,
      from_bus: fromNode ? busName(fromNode) : edge.from_node_id,
      to_bus: toNode ? busName(toNode) : edge.to_node_id,
      length_km: lengthKm(edge),
      r_ohm_per_km: rPerKm(edge),
      x_ohm_per_km: xPerKm(edge),
      rated_current_a: Number(edge.params.rated_current_a ?? (edge.type === 'special_line' ? 400 : 250)),
      voltage_level_kv: lineVoltageKv(edge, fromNode ? voltageKv(fromNode) : 10),
    };
  });

  if (!transformers.length) {
    warnings.push({ level: 'warning', message: '当前拓扑没有 transformer 节点，后续 OpenDSS 基层模型将缺少电源入口。' });
  }

  const connectedLoadIds = new Set<string>();
  for (const edge of model.edges) {
    const fromNode = nodeMap.get(edge.from_node_id);
    const toNode = nodeMap.get(edge.to_node_id);
    if (fromNode?.type === 'load') connectedLoadIds.add(fromNode.id);
    if (toNode?.type === 'load') connectedLoadIds.add(toNode.id);
  }
  for (const loadNode of model.nodes.filter((node) => node.type === 'load')) {
    if (!connectedLoadIds.has(loadNode.id)) {
      warnings.push({ level: 'warning', message: `负荷节点 ${loadNode.name} 未接入任何线路。` });
    }
  }

  for (const edge of model.edges) {
    if (edge.from_node_id === edge.to_node_id) {
      warnings.push({ level: 'warning', message: `线路 ${edge.name} 的起点和终点相同。` });
    }
  }

  const dssLines: string[] = [];
  dssLines.push('! =======================');
  dssLines.push('! OpenDSS mapping preview');
  dssLines.push('! =======================');
  dssLines.push('');
  dssLines.push('! buses');
  for (const bus of buses) {
    dssLines.push(`! ${bus.node_name} -> bus ${bus.bus_name} (${bus.node_type}, ${bus.voltage_level_kv} kV)`);
  }
  dssLines.push('');
  dssLines.push('! transformer placeholders');
  for (const xf of transformers) {
    dssLines.push(`! New Transformer.${xf.dss_name} phases=3 windings=2 buses=(${xf.bus_name},sourcebus) kVs=(${xf.voltage_level_kv},110) kVAs=(${xf.rated_kva},${xf.rated_kva})`);
  }
  dssLines.push('');
  dssLines.push('! lines');
  for (const line of lines) {
    dssLines.push(`New Line.${line.dss_name} Bus1=${line.from_bus}.1 Bus2=${line.to_bus}.1 phases=1 length=${line.length_km} units=km R1=${line.r_ohm_per_km} X1=${line.x_ohm_per_km}`);
  }
  dssLines.push('');
  dssLines.push('! loads (design placeholders, runtime profile applied later)');
  for (const load of loads) {
    const kvLn = (load.voltage_level_kv as number) / Math.sqrt(3);
    dssLines.push(`New Load.${load.dss_name} bus1=${load.bus_name}.1 phases=1 conn=wye kV=${kvLn.toFixed(4)} kW=${load.design_kw} pf=${load.pf}`);
  }

  return {
    buses,
    lines,
    loads,
    transformers,
    warnings,
    dssPreview: dssLines.join('\n'),
  };
}
