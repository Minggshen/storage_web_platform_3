import type {
  DistributionServiceEdgeProfile,
  LoadCategory,
  NodeKind,
  NodeVisualSpec,
  TopologyData,
  TopologyEdge,
  TopologyNode,
} from './topologyTypes';
import {
  BUS_EQUIPMENT_NODE_TYPES,
  CANVAS_HEIGHT,
  CANVAS_WIDTH,
  DEFAULT_LINE_TYPE,
  ECONOMIC_DEFAULT_PARAMS,
  ECONOMIC_PARAM_KEYS,
  EDGE_ADVANCED_PARAM_KEYS,
  LINE_CODE_OPTIONS,
  LINE_STROKE_BY_CODE,
  LOAD_CATEGORY_VISUALS,
  LOAD_PANEL_REMOVED_PARAM_KEYS,
  NODE_ADVANCED_PARAM_KEYS,
  NODE_HEIGHT,
  NODE_HIDDEN_PERSISTED_PARAM_KEYS,
  NODE_REPEL_PADDING,
  NODE_WIDTH,
  RESOURCE_NODE_TYPES,
  SERVICE_LINE_DEFAULT_LENGTH_KM,
  SERVICE_LINE_EMERGENCY_MARGIN,
  SERVICE_LINE_LINECODE,
  SERVICE_LINE_LOW_Z_CURRENT_THRESHOLD_A,
  SERVICE_LINE_MIN_RATED_A,
  SERVICE_LINE_RESOURCE_MARGIN,
  SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN,
  TRANSFORMER_NODE_TYPES,
  WIRE_DATA_CU,
  WIRE_XR_RATIO,
} from './topologyConstants';

// ── Type guards ──

export function isTransformerType(type: string) {
  return TRANSFORMER_NODE_TYPES.has(type);
}

export function isBusEquipmentType(type: string) {
  return BUS_EQUIPMENT_NODE_TYPES.has(type);
}

export function isResourceType(type: string) {
  return RESOURCE_NODE_TYPES.has(type);
}

// ── Math / general helpers ──

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function safeNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

export function roundParamNumber(value: number, digits = 6) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function legacyBool(value: unknown, fallback: boolean) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const text = value.trim().toLowerCase();
    if (['1', 'true', 'yes', 'on', '是', '启用'].includes(text)) return true;
    if (['0', 'false', 'no', 'off', '否', '停用'].includes(text)) return false;
  }
  return fallback;
}

// ── Param accessors ──

export function stringParam(params: Record<string, unknown> | undefined, key: string, fallback: string) {
  const value = params?.[key];
  return typeof value === 'string' ? value : String(value ?? fallback);
}

export function numberParam(params: Record<string, unknown> | undefined, key: string, fallback: number) {
  const value = Number(params?.[key] ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

export function numberInputValue(params: Record<string, unknown> | undefined, key: string) {
  const value = params?.[key];
  if (value === null || value === undefined || value === '') return '';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : '';
}

export function booleanParam(params: Record<string, unknown> | undefined, key: string, fallback: boolean) {
  const value = params?.[key];
  return legacyBool(value, fallback);
}

export function hasPositiveNumberParam(params: Record<string, unknown> | undefined, key: string) {
  const value = params?.[key];
  if (value === null || value === undefined || value === '') return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

// ── Line code helpers ──

export function lineCodeDefaults(linecode: string) {
  return LINE_CODE_OPTIONS.find((item) => item.value === linecode) ?? LINE_CODE_OPTIONS[0];
}

export function edgeLineCodeLabel(linecode: string) {
  return lineCodeDefaults(linecode).label;
}

// ── Power factor / reactive ratio ──

export function derivePowerFactorFromRatio(ratio: number) {
  if (!(Number.isFinite(ratio) && ratio >= 0)) return null;
  return 1 / Math.sqrt(1 + ratio * ratio);
}

export function getLoadReactiveRatio(params: Record<string, unknown> | undefined) {
  const qRatio = Number(params?.q_to_p_ratio);
  if (Number.isFinite(qRatio) && qRatio >= 0) return qRatio;

  const kw = Number(params?.design_kw);
  const kvar = Number(params?.kvar);
  if (Number.isFinite(kw) && kw > 0 && Number.isFinite(kvar) && kvar >= 0) {
    return kvar / kw;
  }

  const pf = Number(params?.pf);
  if (Number.isFinite(pf) && pf > 0 && pf <= 1) {
    return Math.tan(Math.acos(pf));
  }

  return null;
}

export function getLoadPowerFactor(params: Record<string, unknown> | undefined) {
  const ratio = getLoadReactiveRatio(params);
  return ratio == null ? null : derivePowerFactorFromRatio(ratio);
}

export function syncLoadElectricalParams(params: Record<string, unknown>) {
  const next = { ...params };
  const kw = Number(next.design_kw);
  const ratio = Number(next.q_to_p_ratio);
  const kvar = Number(next.kvar);
  const pf = Number(next.pf);

  if (Number.isFinite(kw) && kw > 0) {
    if (Number.isFinite(ratio) && ratio >= 0) {
      next.kvar = roundParamNumber(kw * ratio);
    } else if (Number.isFinite(kvar) && kvar >= 0) {
      next.q_to_p_ratio = roundParamNumber(kvar / kw);
    } else if (Number.isFinite(pf) && pf > 0 && pf <= 1) {
      const phi = Math.acos(pf);
      const derivedRatio = Math.tan(phi);
      next.q_to_p_ratio = roundParamNumber(derivedRatio);
      next.kvar = roundParamNumber(kw * derivedRatio);
    }
  }

  const finalRatio = Number(next.q_to_p_ratio);
  const derivedPf = derivePowerFactorFromRatio(finalRatio);
  if (derivedPf != null) {
    next.pf = roundParamNumber(derivedPf);
  }

  return next;
}

export function cleanLoadPanelParams(params: Record<string, unknown> | undefined) {
  const next = { ...(params ?? {}) };
  const legacyDescription = typeof next.description === 'string' ? next.description.trim() : '';
  const targetKv = Number(next.target_kv_ln);
  const legacyVoltageKv = Number(next.voltage_level_kv);
  if (!(Number.isFinite(targetKv) && targetKv > 0) && Number.isFinite(legacyVoltageKv) && legacyVoltageKv > 0) {
    next.target_kv_ln = legacyVoltageKv;
  }
  for (const key of LOAD_PANEL_REMOVED_PARAM_KEYS) {
    delete next[key];
  }
  if (!next.remarks && legacyDescription) {
    next.remarks = legacyDescription;
  }
  return syncLoadElectricalParams(next);
}

// ── Param picking ──

export function pickParamKeys(
  params: Record<string, unknown> | undefined,
  allowedKeys: readonly string[],
) {
  const source = params ?? {};
  const next: Record<string, unknown> = {};
  for (const key of allowedKeys) {
    if (!(key in source)) continue;
    const value = source[key];
    if (value === undefined || value === null || value === '') continue;
    next[key] = value;
  }
  return next;
}

// ── Node helper: display type ──

export function getDisplayNodeType(node: Pick<TopologyNode, 'type' | 'params'>) {
  return isDistributionTransformerNode(node) ? 'distribution_transformer' : node.type;
}

export function isDistributionTransformerNode(node: Pick<TopologyNode, 'type' | 'params'> | null | undefined) {
  if (!node) return false;
  if (node.type === 'distribution_transformer') return true;
  if (node.type !== 'transformer') return false;
  const role = String(node.params?.transformer_role ?? node.params?.role ?? '').trim().toLowerCase();
  return (
    role === 'distribution' ||
    role === 'distribution_transformer' ||
    role === 'customer_distribution' ||
    booleanParam(node.params, 'is_distribution_transformer', false)
  );
}

export function isLowSideResourceNode(node: Pick<TopologyNode, 'type'> | null | undefined) {
  if (!node) return false;
  return ['load', 'storage', 'pv', 'wind', 'capacitor'].includes(node.type);
}

// ── Editable params ──

export function editableNodeParams(node: TopologyNode | null | undefined) {
  if (!node) return {};
  const displayType = getDisplayNodeType(node);
  const params = node.type === 'load' ? cleanLoadPanelParams(node.params) : { ...(node.params ?? {}) };
  const keys = NODE_ADVANCED_PARAM_KEYS[displayType] ?? [];
  return pickParamKeys(params, keys);
}

export function getHiddenNodeParams(node: TopologyNode) {
  const displayType = getDisplayNodeType(node);
  const hiddenKeys = NODE_HIDDEN_PERSISTED_PARAM_KEYS[displayType] ?? [];
  return pickParamKeys(node.params, hiddenKeys);
}

export function sanitizeNodeParamsForEditor(node: TopologyNode, params: Record<string, unknown>) {
  const displayType = getDisplayNodeType(node);
  const cleaned = node.type === 'load' ? cleanLoadPanelParams(params) : { ...params };
  const editable = pickParamKeys(cleaned, NODE_ADVANCED_PARAM_KEYS[displayType] ?? []);
  return {
    ...getHiddenNodeParams(node),
    ...editable,
  };
}

export function editableEdgeParams(edge: TopologyEdge | null | undefined) {
  if (!edge) return {};
  return pickParamKeys(edge.params, EDGE_ADVANCED_PARAM_KEYS);
}

// ── Economic params ──

export function stripEconomicParams(params: Record<string, unknown>) {
  const next = { ...params };
  ECONOMIC_PARAM_KEYS.forEach((key) => {
    delete next[key];
  });
  return next;
}

export function collectLegacyEconomicParams(node: Partial<TopologyNode>) {
  const params = isRecord(node.params) ? node.params : {};
  const migrated: Record<string, unknown> = {};
  ECONOMIC_PARAM_KEYS.forEach((key) => {
    if (params[key] !== undefined) migrated[key] = params[key];
  });
  return migrated;
}

export function extractLegacyEconomicParams(nodes: Partial<TopologyNode>[]) {
  const preferredNodes = nodes.filter((node) => {
    const params = isRecord(node.params) ? node.params : {};
    return String(node.type ?? '').trim().toLowerCase() === 'load' && legacyBool(params.optimize_storage, false);
  });
  for (const node of [...preferredNodes, ...nodes]) {
    const migrated = collectLegacyEconomicParams(node);
    if (Object.keys(migrated).length > 0) return migrated;
  }
  return {};
}

export function normalizeEconomicParams(input: unknown, legacy: Record<string, unknown> = {}) {
  const current = isRecord(input) ? input : {};
  const demandCharge =
    current.demand_charge_yuan_per_kw_month ??
    current.daily_demand_shadow_yuan_per_kw ??
    legacy.demand_charge_yuan_per_kw_month ??
    legacy.daily_demand_shadow_yuan_per_kw ??
    ECONOMIC_DEFAULT_PARAMS.demand_charge_yuan_per_kw_month;
  const merged = {
    ...ECONOMIC_DEFAULT_PARAMS,
    ...legacy,
    ...current,
  };
  return {
    ...merged,
    demand_charge_yuan_per_kw_month: demandCharge,
    daily_demand_shadow_yuan_per_kw: demandCharge,
  };
}

export function stringifyEconomicParams(input: unknown) {
  return JSON.stringify(normalizeEconomicParams(input));
}

// ── Normalization ──

export function normalizeNode(node: Partial<TopologyNode>, index: number): TopologyNode {
  const x = safeNumber(node.position?.x, 120 + index * 50);
  const y = safeNumber(node.position?.y, 120 + index * 40);
  const rawParams = typeof node.params === 'object' && node.params !== null ? { ...node.params } : {};
  const type = String(node.type ?? 'load');
  const strippedParams = stripEconomicParams(rawParams);
  const params = type === 'load' ? cleanLoadPanelParams(strippedParams) : strippedParams;
  params.phases = 3;
  if ((type === 'grid' || type === 'source') && Math.abs(Number(params.base_kv) - 110 / Math.sqrt(3)) <= 0.5) {
    params.base_kv = 110;
  }
  if (isTransformerType(type) && Math.abs(Number(params.primary_voltage_kv) - 110 / Math.sqrt(3)) <= 0.5) {
    params.primary_voltage_kv = 110;
  }
  if (type === 'load' && Math.abs(Number(params.target_kv_ln) - 10 / Math.sqrt(3)) <= 0.2) {
    params.target_kv_ln = 10;
  }
  if (type === 'load' && params.allow_grid_export === undefined) {
    params.allow_grid_export = legacyBool(params.allow_reverse_power_to_grid ?? params.allow_export_to_grid, false);
  }
  return {
    id: String(node.id ?? `node_${index + 1}`),
    type,
    name:
      typeof node.name === 'string' && node.name.trim()
        ? node.name
        : String(node.id ?? `node_${index + 1}`),
    position: { x, y },
    params,
    runtime_binding: node.runtime_binding ?? null,
    tags: Array.isArray(node.tags) ? node.tags.map(String) : [],
  };
}

export function normalizeEdge(edge: Partial<TopologyEdge>, index: number): TopologyEdge {
  const params = typeof edge.params === 'object' && edge.params !== null ? { ...edge.params } : {};
  params.phases = 3;
  const rawType = String(edge.type ?? DEFAULT_LINE_TYPE);
  return {
    id: String(edge.id ?? `line_${index + 1}`),
    type: rawType === 'line' ? DEFAULT_LINE_TYPE : rawType,
    name:
      typeof edge.name === 'string' && edge.name.trim()
        ? edge.name
        : String(edge.id ?? `line_${index + 1}`),
    from_node_id: String(edge.from_node_id ?? ''),
    to_node_id: String(edge.to_node_id ?? ''),
    params,
  };
}

export function normalizeTopology(input: unknown): TopologyData {
  const obj = (input ?? {}) as Record<string, unknown>;
  const rawNodes = Array.isArray(obj.nodes) ? (obj.nodes as Partial<TopologyNode>[]) : [];
  const rawEdges = Array.isArray(obj.edges) ? (obj.edges as Partial<TopologyEdge>[]) : [];
  const legacyEconomicParams = extractLegacyEconomicParams(rawNodes);
  return {
    nodes: rawNodes.map(normalizeNode),
    edges: rawEdges.map(normalizeEdge),
    economic_parameters: normalizeEconomicParams(obj.economic_parameters, legacyEconomicParams),
  };
}

export function stringifyTopology(data: TopologyData) {
  return JSON.stringify(data, null, 2);
}

// ── Load category visuals ──

export function getLoadCategory(value: unknown): LoadCategory {
  const text = String(value ?? '').trim().toLowerCase();
  if (text === 'commercial' || text === '商业') return 'commercial';
  if (text === 'residential' || text === '居民') return 'residential';
  return 'industrial';
}

export function getLoadCategoryVisual(value: unknown) {
  return LOAD_CATEGORY_VISUALS[getLoadCategory(value)];
}

// ── Node visuals ──

export function getNodeVisual(type: string): NodeVisualSpec {
  switch (type) {
    case 'grid':
    case 'source':
      return { color: '#dc2626', border: '#f87171', background: '#fff1f2', radius: 999, width: 126, height: 58 };
    case 'transformer':
      return { color: '#d97706', border: '#f59e0b', background: '#fffbeb', radius: 16, width: 128, height: 64 };
    case 'distribution_transformer':
      return { color: '#a16207', border: '#facc15', background: '#fefce8', radius: 14, width: 128, height: 64 };
    case 'bus':
      return { color: '#2563eb', border: '#60a5fa', background: '#eff6ff', radius: 999, width: 138, height: 44 };
    case 'ring_main_unit':
      return { color: '#475569', border: '#94a3b8', background: '#f8fafc', radius: 12, width: 126, height: 62, clipPath: 'polygon(10px 0, calc(100% - 10px) 0, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0 calc(100% - 10px), 0 10px)' };
    case 'branch':
      return { color: '#0f766e', border: '#2dd4bf', background: '#ecfdf5', radius: 999, width: 70, height: 70 };
    case 'switch':
      return { color: '#334155', border: '#94a3b8', background: '#f8fafc', radius: 10, width: 104, height: 54 };
    case 'breaker':
      return { color: '#991b1b', border: '#fca5a5', background: '#fef2f2', radius: 10, width: 104, height: 54 };
    case 'fuse':
      return { color: '#9333ea', border: '#c4b5fd', background: '#faf5ff', radius: 10, width: 104, height: 54 };
    case 'regulator':
      return { color: '#0369a1', border: '#7dd3fc', background: '#f0f9ff', radius: 12, width: 118, height: 58 };
    case 'capacitor':
      return { color: '#0284c7', border: '#38bdf8', background: '#f0f9ff', radius: 999, width: 86, height: 56 };
    case 'pv':
      return { color: '#2563eb', border: '#93c5fd', background: '#eff6ff', radius: 12, width: 112, height: 60 };
    case 'wind':
      return { color: '#0f766e', border: '#5eead4', background: '#ecfdf5', radius: 999, width: 92, height: 60 };
    case 'storage':
      return { color: '#475569', border: '#94a3b8', background: '#f8fafc', radius: 12, width: 112, height: 60 };
    case 'load':
      return { color: '#059669', border: '#34d399', background: '#f0fdf4', radius: '18px 18px 8px 8px', width: 128, height: 62 };
    default:
      return { color: '#64748b', border: '#cbd5e1', background: '#ffffff', radius: 12, width: NODE_WIDTH, height: NODE_HEIGHT };
  }
}

export function getNodeVisualForNode(node: TopologyNode): NodeVisualSpec {
  if (node.type === 'load') return getLoadCategoryVisual(node.params?.category);
  return getNodeVisual(getDisplayNodeType(node));
}

export function getNodeSize(type: string) {
  const visual = getNodeVisual(type);
  return { width: visual.width, height: visual.height };
}

export function getNodeSizeForNode(node: TopologyNode) {
  const visual = getNodeVisualForNode(node);
  return { width: visual.width, height: visual.height };
}

// ── Node shape / geometry ──

export function getNodeAnchorShape(node: TopologyNode) {
  const displayType = getDisplayNodeType(node);
  switch (displayType) {
    case 'grid':
    case 'source':
    case 'bus':
    case 'branch':
    case 'capacitor':
    case 'wind':
      return 'ellipse';
    default:
      return 'rect';
  }
}

export function getNodeCenter(node: TopologyNode) {
  const size = getNodeSizeForNode(node);
  return {
    x: safeNumber(node.position?.x, 100) + size.width / 2,
    y: safeNumber(node.position?.y, 100) + size.height / 2,
  };
}

export function getNodeBoundaryPoint(node: TopologyNode, toward: { x: number; y: number }) {
  const size = getNodeSizeForNode(node);
  const center = getNodeCenter(node);
  const dx = toward.x - center.x;
  const dy = toward.y - center.y;
  if (Math.abs(dx) < 0.001 && Math.abs(dy) < 0.001) return center;

  const distance = Math.hypot(dx, dy);
  const overshoot = 1.5;

  if (getNodeAnchorShape(node) === 'ellipse') {
    const rx = Math.max(1, size.width / 2 - 2);
    const ry = Math.max(1, size.height / 2 - 2);
    const ellipseScale = Math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry));
    const boundaryX = center.x + dx / ellipseScale;
    const boundaryY = center.y + dy / ellipseScale;
    const push = distance > 0.001 ? overshoot / distance : 0;
    return { x: boundaryX + dx * push, y: boundaryY + dy * push };
  }

  const halfWidth = Math.max(1, size.width / 2 - 2);
  const halfHeight = Math.max(1, size.height / 2 - 2);
  const xScale = Math.abs(dx) > 0.001 ? halfWidth / Math.abs(dx) : Number.POSITIVE_INFINITY;
  const yScale = Math.abs(dy) > 0.001 ? halfHeight / Math.abs(dy) : Number.POSITIVE_INFINITY;
  const scale = Math.min(xScale, yScale, 1);
  const push = distance > 0.001 ? overshoot / distance : 0;
  return { x: center.x + dx * (scale + push), y: center.y + dy * (scale + push) };
}

export function resolveNodeOverlaps(nodes: TopologyNode[], lockedNodeId?: string) {
  const rects = nodes.map((node) => {
    const size = getNodeSizeForNode(node);
    return {
      id: node.id,
      x: safeNumber(node.position?.x, 100),
      y: safeNumber(node.position?.y, 100),
      width: size.width,
      height: size.height,
    };
  });

  for (let iteration = 0; iteration < 90; iteration += 1) {
    let moved = false;
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        const a = rects[i];
        const b = rects[j];
        const overlapX = Math.min(a.x + a.width + NODE_REPEL_PADDING - b.x, b.x + b.width + NODE_REPEL_PADDING - a.x);
        const overlapY = Math.min(a.y + a.height + NODE_REPEL_PADDING - b.y, b.y + b.height + NODE_REPEL_PADDING - a.y);
        if (overlapX <= 0 || overlapY <= 0) continue;

        const aLocked = a.id === lockedNodeId;
        const bLocked = b.id === lockedNodeId;
        if (aLocked && bLocked) continue;

        const dx = a.x + a.width / 2 - (b.x + b.width / 2) || (i % 2 === 0 ? -1 : 1);
        const dy = a.y + a.height / 2 - (b.y + b.height / 2) || (j % 2 === 0 ? -1 : 1);
        const move = Math.min(overlapX, overlapY) / (aLocked || bLocked ? 1 : 2) + 1;

        if (overlapX < overlapY) {
          const direction = dx < 0 ? -1 : 1;
          if (!aLocked) a.x = clamp(a.x + direction * move, 0, CANVAS_WIDTH - a.width);
          if (!bLocked) b.x = clamp(b.x - direction * move, 0, CANVAS_WIDTH - b.width);
        } else {
          const direction = dy < 0 ? -1 : 1;
          if (!aLocked) a.y = clamp(a.y + direction * move, 0, CANVAS_HEIGHT - a.height);
          if (!bLocked) b.y = clamp(b.y - direction * move, 0, CANVAS_HEIGHT - b.height);
        }
        moved = true;
      }
    }
    if (!moved) break;
  }

  const positionById = new Map(rects.map((rect) => [rect.id, { x: Math.round(rect.x), y: Math.round(rect.y) }]));
  return nodes.map((node) => ({
    ...node,
    position: positionById.get(node.id) ?? node.position,
  }));
}

// ── Node labels ──

export function getNodeLabel(type: string) {
  switch (type) {
    case 'grid': return '电网/电源';
    case 'source': return '电源';
    case 'transformer': return '主变';
    case 'distribution_transformer': return '用户配变';
    case 'bus': return '母线';
    case 'ring_main_unit': return '环网柜';
    case 'branch': return '分支点';
    case 'switch': return '开关';
    case 'breaker': return '断路器';
    case 'fuse': return '熔断器';
    case 'regulator': return '电压调节';
    case 'capacitor': return '电容器';
    case 'pv': return '光伏';
    case 'wind': return '风机';
    case 'storage': return '储能';
    case 'load': return '负荷';
    default: return type;
  }
}

export function getNodeLabelForNode(node: Pick<TopologyNode, 'type' | 'params'>) {
  return getNodeLabel(getDisplayNodeType(node));
}

export function getLoadNodeCode(node: TopologyNode) {
  const params = node.params ?? {};
  const dssLoadName = stringParam(params, 'dss_load_name', '').trim();
  if (dssLoadName) return dssLoadName;

  const nodeId = numberParam(params, 'node_id', 0);
  if (nodeId > 0) return `LD${String(Math.round(nodeId)).padStart(2, '0')}`;

  const fallbackName = String(node.name ?? node.id).trim();
  return fallbackName || node.id;
}

export function getNodeDetail(node: TopologyNode) {
  const params = node.params ?? {};
  const phases = numberParam(params, 'phases', 3);
  const displayType = getDisplayNodeType(node);
  switch (displayType) {
    case 'grid':
    case 'source': {
      const baseKv = numberParam(params, 'base_kv', 110);
      return `${baseKv} kV / ${phases}相`;
    }
    case 'transformer': {
      const rated = numberParam(params, 'rated_kva', 31500);
      const kv = numberParam(params, 'voltage_level_kv', 10);
      return `${Math.round(rated)} kVA / ${kv} kV`;
    }
    case 'distribution_transformer': {
      const rated = numberParam(params, 'rated_kva', 1000);
      const primaryKv = numberParam(params, 'primary_voltage_kv', 10);
      const secondaryKv = numberParam(params, 'voltage_level_kv', 0.4);
      return `${Math.round(rated)} kVA / ${primaryKv}/${secondaryKv} kV`;
    }
    case 'bus':
      return `${numberParam(params, 'voltage_level_kv', 10)} kV 母线`;
    case 'ring_main_unit':
      return `${phases}相开关单元`;
    case 'switch':
    case 'breaker':
    case 'fuse':
      return `${numberParam(params, 'voltage_level_kv', 10)} kV ${getNodeLabel(displayType)}`;
    case 'regulator':
      return `${stringParam(params, 'target_transformer', '') || '未指定变压器'} 调压`;
    case 'capacitor':
      return `${numberParam(params, 'kvar', 300)} kvar / ${numberParam(params, 'voltage_level_kv', 10)} kV`;
    case 'pv':
      return `${numberParam(params, 'pmpp_kw', 100)} kW / ${numberParam(params, 'voltage_level_kv', 0.4)} kV`;
    case 'wind':
      return `${numberParam(params, 'rated_kw', 100)} kW / ${numberParam(params, 'voltage_level_kv', 0.4)} kV`;
    case 'storage':
      return `${numberParam(params, 'rated_kw', 100)} kW / ${numberParam(params, 'rated_kwh', 215)} kWh`;
    case 'branch':
      return `${phases}相连接点`;
    case 'load': {
      const kw = numberParam(params, 'design_kw', 0);
      const kv = numberParam(params, 'target_kv_ln', 10);
      const nodeId = numberParam(params, 'node_id', 0);
      const busName = stringParam(params, 'dss_bus_name', '').trim() || (nodeId > 0 ? `n${Math.round(nodeId)}` : '');
      const busPrefix = busName ? `${busName} / ` : '';
      if (kw > 0) return `${busPrefix}${Math.round(kw)} kW / ${kv} kV`;
      return `${busPrefix}${kv} kV`;
    }
    default:
      return `${phases}相元件`;
  }
}

// ── Default params per node kind ──

export function buildNodeDefaultParams(type: NodeKind) {
  switch (type) {
    case 'grid':
      return { base_kv: 110, pu: 1.0, phases: 3, source_bus: 'sourcebus', mvasc3: 1000, mvasc1: 1000, x1r1: 10, x0r0: 3 };
    case 'transformer':
      return { rated_kva: 31500, voltage_level_kv: 10, primary_voltage_kv: 110, primary_bus_name: 'sourcebus', dss_bus_name: 'n0', primary_conn: 'wye', secondary_conn: 'wye', xhl_percent: 7, percent_r: 0.5, tap: 1, phases: 3 };
    case 'distribution_transformer':
      return { enabled: true, rated_kva: 1000, primary_voltage_kv: 10, voltage_level_kv: 0.4, primary_bus_name: '', dss_bus_name: '', secondary_bus_name: '', primary_conn: 'delta', secondary_conn: 'wye', xhl_percent: 6, percent_r: 1, tap: 1, phases: 3 };
    case 'bus':
      return { voltage_level_kv: 10, dss_bus_name: '', phases: 3 };
    case 'ring_main_unit':
      return { voltage_level_kv: 10, dss_bus_name: '', phases: 3 };
    case 'branch':
      return { dss_bus_name: '', voltage_level_kv: 10, phases: 3 };
    case 'switch':
      return { enabled: true, normally_open: false, dss_bus_name: '', voltage_level_kv: 10, target_line: '', phases: 3 };
    case 'breaker':
      return { enabled: true, normally_open: false, dss_bus_name: '', voltage_level_kv: 10, target_line: '', phases: 3 };
    case 'fuse':
      return { enabled: true, normally_open: false, dss_bus_name: '', voltage_level_kv: 10, target_line: '', rated_current_a: 200, phases: 3 };
    case 'regulator':
      return { enabled: true, dss_bus_name: '', voltage_level_kv: 10, target_transformer: '', winding: 2, vreg: 120, band: 2, ptratio: 60, phases: 3 };
    case 'capacitor':
      return { enabled: true, dss_bus_name: '', voltage_level_kv: 10, kvar: 300, connection: 'wye', phases: 3 };
    case 'pv':
      return { enabled: true, dss_bus_name: '', dss_name: '', voltage_level_kv: 0.4, pmpp_kw: 100, kva: 110, pf: 1, irradiance: 1, phases: 3 };
    case 'wind':
      return { enabled: true, dss_bus_name: '', dss_name: '', voltage_level_kv: 0.4, rated_kw: 100, pf: 0.98, phases: 3 };
    case 'storage':
      return { enabled: true, dss_bus_name: '', dss_name: '', voltage_level_kv: 0.4, rated_kw: 100, rated_kwh: 215, initial_soc_pct: 50, reserve_soc_pct: 10, phases: 3 };
    case 'load':
      return { enabled: true, node_id: null, dss_bus_name: '', dss_load_name: '', target_kv_ln: null, phases: 3, category: 'industrial', remarks: '', model_year: 2025, q_to_p_ratio: 0.25, pf: 0.95, optimize_storage: true, allow_grid_export: false, transformer_capacity_kva: 1000, transformer_pf_limit: 0.95, transformer_reserve_ratio: 0.15, dispatch_mode: 'hybrid', run_mode: 'single_user' };
    default:
      return {};
  }
}

// ── Edge helpers ──

export function getDistributionServiceEdgeNodes(
  edge: Pick<TopologyEdge, 'from_node_id' | 'to_node_id'>,
  nodeMap: Map<string, TopologyNode>,
) {
  const fromNode = nodeMap.get(edge.from_node_id);
  const toNode = nodeMap.get(edge.to_node_id);
  if (!fromNode || !toNode) return null;
  if (isDistributionTransformerNode(fromNode) && isLowSideResourceNode(toNode)) {
    return { transformerNode: fromNode, resourceNode: toNode };
  }
  if (isDistributionTransformerNode(toNode) && isLowSideResourceNode(fromNode)) {
    return { transformerNode: toNode, resourceNode: fromNode };
  }
  return null;
}

export function threePhaseCurrentFromKva(kva: number, kvLl: number) {
  if (kva <= 0 || kvLl <= 0) return 0;
  return kva / (Math.sqrt(3) * kvLl);
}

export function buildDistributionServiceEdgeProfile(
  transformerKva: number,
  resourceKva: number,
  secondaryKv: number,
): DistributionServiceEdgeProfile | null {
  const transformerCurrentA = threePhaseCurrentFromKva(transformerKva, secondaryKv);
  const resourceCurrentA = threePhaseCurrentFromKva(resourceKva, secondaryKv);
  if (transformerCurrentA <= 0 && resourceCurrentA <= 0) return null;
  const ratedCurrentA = Math.max(transformerCurrentA, resourceCurrentA * SERVICE_LINE_RESOURCE_MARGIN, SERVICE_LINE_MIN_RATED_A);
  const emergCurrentA = Math.max(
    ratedCurrentA * SERVICE_LINE_EMERGENCY_MARGIN,
    transformerCurrentA * SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN,
    ratedCurrentA,
  );
  return {
    linecode: SERVICE_LINE_LINECODE,
    defaultLengthKm: SERVICE_LINE_DEFAULT_LENGTH_KM,
    secondaryKv,
    transformerKva,
    resourceKva,
    transformerCurrentA,
    resourceCurrentA,
    ratedCurrentA,
    emergCurrentA,
  };
}

export function resourceApparentPowerKva(node: TopologyNode) {
  const params = node.params ?? {};
  switch (node.type) {
    case 'load': {
      const kw = numberParam(params, 'design_kw', 0);
      const kvar = numberParam(params, 'kvar', kw * numberParam(params, 'q_to_p_ratio', 0.25));
      return Math.hypot(kw, kvar);
    }
    case 'storage': {
      const kva = numberParam(params, 'kva', 0);
      if (kva > 0) return kva;
      return Math.max(numberParam(params, 'rated_kw', 0), numberParam(params, 'rated_kwh', 0));
    }
    case 'pv':
      return numberParam(params, 'kva', numberParam(params, 'pmpp_kw', numberParam(params, 'rated_kw', 0)));
    case 'wind': {
      const ratedKw = numberParam(params, 'rated_kw', 0);
      const pf = Math.abs(numberParam(params, 'pf', 0.98));
      if (pf <= 0) return ratedKw;
      return ratedKw / Math.min(pf, 1);
    }
    case 'capacitor':
      return Math.abs(numberParam(params, 'kvar', 0));
    default:
      return 0;
  }
}

export function getDistributionServiceEdgeProfile(
  edge: Pick<TopologyEdge, 'from_node_id' | 'to_node_id'>,
  nodeMap: Map<string, TopologyNode>,
) {
  const pair = getDistributionServiceEdgeNodes(edge, nodeMap);
  if (!pair) return null;
  const transformerParams = pair.transformerNode.params ?? {};
  const secondaryKv = numberParam(transformerParams, 'voltage_level_kv', 0.4);
  const transformerKva = numberParam(transformerParams, 'rated_kva', 1000);
  const resourceKva = resourceApparentPowerKva(pair.resourceNode);
  return buildDistributionServiceEdgeProfile(transformerKva, resourceKva, secondaryKv);
}

export function edgeVisualMeta(edge: TopologyEdge, nodeMap: Map<string, TopologyNode>) {
  const serviceProfile = getDistributionServiceEdgeProfile(edge, nodeMap);
  if (serviceProfile) {
    return {
      categoryLabel: '用户低压接入线（自动）',
      shortLabel: '低压接入',
      stroke: '#d97706',
      dash: undefined as string | undefined,
      serviceProfile,
    };
  }
  if (booleanParam(edge.params, 'normally_open', false)) {
    return {
      categoryLabel: '常开联络线',
      shortLabel: '联络线',
      stroke: '#7c3aed',
      dash: '8 6',
      serviceProfile: null,
    };
  }
  const linecode = stringParam(edge.params, 'linecode', 'LC_MAIN');
  return {
    categoryLabel: edgeLineCodeLabel(linecode),
    shortLabel: edgeLineCodeLabel(linecode),
    stroke: LINE_STROKE_BY_CODE[linecode] ?? (edge.type === 'special_line' ? '#2563eb' : '#55708c'),
    dash: undefined as string | undefined,
    serviceProfile: null,
  };
}

export function formatCurrentDisplay(currentA: number) {
  if (!Number.isFinite(currentA) || currentA <= 0) return '--';
  if (currentA >= 1000) return `${(currentA / 1000).toFixed(currentA >= 10000 ? 1 : 2)} kA`;
  return `${Math.round(currentA)} A`;
}

// ── Edge auto-inference (used by both utils and component) ──

function _selectParallelCable(requiredAmpA: number) {
  const candidates = WIRE_DATA_CU.map((cable) => {
    const n = Math.min(12, Math.max(1, Math.ceil(requiredAmpA / cable.normamps)));
    return { name: cable.name, rac: cable.rac, normamps: cable.normamps * n, parallel: n };
  });
  const best = candidates.sort((a, b) => a.normamps - b.normamps).find((c) => c.normamps >= requiredAmpA);
  return best ?? { name: '1000_CU', rac: 0.042875, normamps: 1300, parallel: 1 };
}

export function getNormalEdgeCurrent(
  fromNode: TopologyNode | undefined,
  toNode: TopologyNode | undefined,
): number {
  const txNode = isDistributionTransformerNode(fromNode) ? fromNode :
                 isDistributionTransformerNode(toNode) ? toNode :
                 (isTransformerType(fromNode?.type ?? '') ? fromNode :
                  isTransformerType(toNode?.type ?? '') ? toNode : undefined);
  if (!txNode) return 0;
  const txParams = txNode.params ?? {};
  const primaryKv = numberParam(txParams, 'voltage_level_kv', 10.0);
  const ratedKva = numberParam(txParams, 'rated_kva', 0);
  return threePhaseCurrentFromKva(ratedKva, primaryKv);
}

export function selectLineCodeByCurrent(currentA: number): { linecode: string; rated_current_a: number; emerg_current_a: number } {
  if (currentA <= 0) return { linecode: 'LC_LIGHT', rated_current_a: 300, emerg_current_a: 450 };
  const option = LINE_CODE_OPTIONS.find(opt => opt.rated_current_a >= currentA);
  return option
    ? { linecode: option.value, rated_current_a: option.rated_current_a, emerg_current_a: option.emerg_current_a }
    : { linecode: 'LC_CABLE', rated_current_a: 1400, emerg_current_a: 1700 };
}

export function inferAutoEdgeParams(
  fromNode: TopologyNode | undefined,
  toNode: TopologyNode | undefined,
): { params: Record<string, unknown>; edgeType: 'normal_line' | 'special_line' } {
  const isServiceEdge =
    (isDistributionTransformerNode(fromNode) && isLowSideResourceNode(toNode)) ||
    (isDistributionTransformerNode(toNode) && isLowSideResourceNode(fromNode));

  if (isServiceEdge) {
    const txNode = isDistributionTransformerNode(fromNode) ? fromNode : toNode;
    const resNode = isDistributionTransformerNode(fromNode) ? toNode : fromNode;
    const txParams = txNode?.params ?? {};
    const secondaryKv = numberParam(txParams, 'voltage_level_kv', 0.4);
    const transformerKva = numberParam(txParams, 'rated_kva', 1000);
    const resourceKva = resNode ? resourceApparentPowerKva(resNode) : 0;
    const transformerCurrentA = threePhaseCurrentFromKva(transformerKva, secondaryKv);
    const resourceCurrentA = threePhaseCurrentFromKva(resourceKva, secondaryKv);
    const ratedCurrentA = Math.max(transformerCurrentA, resourceCurrentA * SERVICE_LINE_RESOURCE_MARGIN, SERVICE_LINE_MIN_RATED_A);
    const emergCurrentA = Math.max(
      ratedCurrentA * SERVICE_LINE_EMERGENCY_MARGIN,
      transformerCurrentA * SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN,
      ratedCurrentA,
    );

    if (ratedCurrentA >= SERVICE_LINE_LOW_Z_CURRENT_THRESHOLD_A && secondaryKv < 1.0) {
      const cable = _selectParallelCable(ratedCurrentA);
      const r1 = cable.rac / cable.parallel;
      const x1 = r1 * WIRE_XR_RATIO;
      return {
        params: {
          length_km: SERVICE_LINE_DEFAULT_LENGTH_KM,
          linecode: '',
          r_ohm_per_km: r1, x_ohm_per_km: x1,
          r0_ohm_per_km: r1, x0_ohm_per_km: x1,
          c1_nf_per_km: 0, c0_nf_per_km: 0,
          rated_current_a: ratedCurrentA, emerg_current_a: emergCurrentA,
          enabled: true, normally_open: false, phases: 3,
        },
        edgeType: 'special_line',
      };
    }

    return {
      params: {
        length_km: SERVICE_LINE_DEFAULT_LENGTH_KM,
        linecode: SERVICE_LINE_LINECODE,
        r_ohm_per_km: lineCodeDefaults(SERVICE_LINE_LINECODE).r_ohm_per_km,
        x_ohm_per_km: lineCodeDefaults(SERVICE_LINE_LINECODE).x_ohm_per_km,
        rated_current_a: ratedCurrentA, emerg_current_a: emergCurrentA,
        enabled: true, normally_open: false, phases: 3,
      },
      edgeType: 'special_line',
    };
  }

  const edgeCurrentA = getNormalEdgeCurrent(fromNode, toNode);
  const { linecode: autoLinecode, rated_current_a, emerg_current_a } = selectLineCodeByCurrent(edgeCurrentA);
  const selected = lineCodeDefaults(autoLinecode);
  return {
    params: {
      length_km: 0.5,
      linecode: autoLinecode,
      r_ohm_per_km: selected.r_ohm_per_km, x_ohm_per_km: selected.x_ohm_per_km,
      r0_ohm_per_km: selected.r0_ohm_per_km, x0_ohm_per_km: selected.x0_ohm_per_km,
      c1_nf_per_km: selected.c1_nf_per_km, c0_nf_per_km: selected.c0_nf_per_km,
      rated_current_a, emerg_current_a,
      enabled: true, normally_open: false, phases: 3,
    },
    edgeType: 'normal_line',
  };
}

// ── DSS preview ──

export function phaseSuffix(phases: number) {
  return phases === 1 ? '.1' : '.1.2.3';
}

export function dssSafeName(value: string) {
  return value.replace(/[^A-Za-z0-9_]/g, '_').replace(/^_+|_+$/g, '') || 'unnamed';
}

export function nodeDssBusName(node: TopologyNode) {
  const params = node.params ?? {};
  const explicit = stringParam(params, 'dss_bus_name', '').trim() || stringParam(params, 'bus_name', '').trim();
  if (explicit) return dssSafeName(explicit);
  if (node.type === 'grid' || node.type === 'source') return dssSafeName(stringParam(params, 'source_bus', 'sourcebus'));
  if (isTransformerType(node.type)) {
    const fallback = node.type === 'transformer' ? 'n0' : `${dssSafeName(node.id)}_lv`;
    return dssSafeName(stringParam(params, 'secondary_bus_name', fallback));
  }
  if (node.type === 'load') {
    const nodeId = numberParam(params, 'node_id', 0);
    if (nodeId > 0) return `n${nodeId}`;
  }
  return dssSafeName(node.id);
}

export function nodeDssLoadName(node: TopologyNode) {
  const params = node.params ?? {};
  const explicit = stringParam(params, 'dss_load_name', '').trim() || stringParam(params, 'load_name', '').trim();
  if (explicit) return dssSafeName(explicit);
  const nodeId = numberParam(params, 'node_id', 0);
  return nodeId > 0 ? `LD${String(nodeId).padStart(2, '0')}` : dssSafeName(node.id);
}

export function buildDssPreview(topology: TopologyData) {
  const phaseCount = 3;
  const sourceNode = topology.nodes.find((node) => node.type === 'grid' || node.type === 'source');
  const sourceKv = numberParam(sourceNode?.params, 'base_kv', 110);
  const header = [
    '! visual topology preview',
    'Clear',
    'Set DefaultBaseFrequency=50',
    `New Circuit.VisualModel basekv=${sourceKv} pu=1.0 phases=3 bus1=sourcebus${phaseSuffix(phaseCount)}`,
    '',
    'Redirect LineCodes_Custom.dss',
  ];

  const nodeLines = topology.nodes.map((node) => {
    const phases = 3;
    const suffix = phaseSuffix(phases);
    if (node.type === 'grid' || node.type === 'source') {
      const kv = node.params?.base_kv ?? 110;
      const pu = node.params?.pu ?? 1.0;
      return `! grid source ${node.id} / ${node.name} / ${nodeDssBusName(node)} / phases=${phases} / basekv=${kv} / pu=${pu}`;
    }
    if (isTransformerType(node.type)) {
      const rated = node.params?.rated_kva ?? 31500;
      const kv = node.params?.voltage_level_kv ?? 10;
      return `! transformer node ${node.id} / ${node.name} / bus=${nodeDssBusName(node)} / phases=${phases} / rated_kva=${rated} / kv=${kv}`;
    }
    if (node.type === 'load') {
      const kv = Number(node.params?.target_kv_ln ?? 10);
      const pf = Number(node.params?.pf ?? 0.95);
      const kw = Number(node.params?.design_kw ?? 100);
      return `New Load.${nodeDssLoadName(node)} bus1=${nodeDssBusName(node)}${suffix} phases=${phases} conn=wye kv=${kv} kw=${kw} pf=${pf}`;
    }
    if (node.type === 'pv') {
      const kv = Number(node.params?.voltage_level_kv ?? 0.4);
      const pmpp = Number(node.params?.pmpp_kw ?? 100);
      const kva = Number(node.params?.kva ?? pmpp);
      return `New PVSystem.${dssSafeName(String(node.params?.dss_name || node.id))} bus1=${nodeDssBusName(node)}${suffix} phases=${phases} kV=${kv} kVA=${kva} Pmpp=${pmpp}`;
    }
    if (node.type === 'wind') {
      const kv = Number(node.params?.voltage_level_kv ?? 0.4);
      const kw = Number(node.params?.rated_kw ?? 100);
      return `New Generator.${dssSafeName(String(node.params?.dss_name || node.id))} bus1=${nodeDssBusName(node)}${suffix} phases=${phases} kV=${kv} kW=${kw} pf=${Number(node.params?.pf ?? 0.98)}`;
    }
    if (node.type === 'storage') {
      const kv = Number(node.params?.voltage_level_kv ?? 0.4);
      const kw = Number(node.params?.rated_kw ?? 100);
      const kwh = Number(node.params?.rated_kwh ?? 215);
      return `New Storage.${dssSafeName(String(node.params?.dss_name || node.id))} bus1=${nodeDssBusName(node)}${suffix} phases=${phases} kV=${kv} kWrated=${kw} kWhrated=${kwh} dispmode=external`;
    }
    if (node.type === 'capacitor') {
      const kv = Number(node.params?.voltage_level_kv ?? 10);
      const kvar = Number(node.params?.kvar ?? 300);
      return `New Capacitor.${dssSafeName(String(node.params?.dss_name || node.id))} bus1=${nodeDssBusName(node)}${suffix} phases=${phases} kV=${kv} kvar=${kvar}`;
    }
    return `! node ${node.id} / ${node.type} / ${node.name} / bus=${nodeDssBusName(node)} / phases=${phases}`;
  });

  const edgeLines = topology.edges.map((edge) => {
    const length = Number(edge.params?.length_km ?? 1);
    const r = Number(edge.params?.r_ohm_per_km ?? 0.38);
    const x = Number(edge.params?.x_ohm_per_km ?? 0.12);
    const linecode = stringParam(edge.params, 'linecode', 'LC_MAIN');
    const phases = 3;
    const fromNode = topology.nodes.find((node) => node.id === edge.from_node_id);
    const toNode = topology.nodes.find((node) => node.id === edge.to_node_id);
    const fromBus = fromNode ? nodeDssBusName(fromNode) : edge.from_node_id;
    const toBus = toNode ? nodeDssBusName(toNode) : edge.to_node_id;
    const electrical = linecode ? `linecode=${linecode}` : `r1=${r} x1=${x}`;
    return `New Line.${edge.id} bus1=${fromBus}${phaseSuffix(phases)} bus2=${toBus}${phaseSuffix(phases)} phases=${phases} length=${length} units=km ${electrical}`;
  });

  return [...header, ...nodeLines, '', ...edgeLines].join('\n');
}
