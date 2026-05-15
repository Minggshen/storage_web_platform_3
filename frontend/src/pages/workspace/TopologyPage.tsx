import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { fetchSearchSpaceInference, type SearchSpaceInferenceExplainItem, type SearchSpaceInferenceRow } from '../../services/build';
import { fetchProjectTopology, saveProjectTopology, fetchTemplates, saveTemplate, fetchTemplateDetail } from '../../services/topology';
import type { TemplateMeta } from '../../services/topology';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';

type NodeKind =
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
type EdgeKind = 'line' | 'normal_line' | 'special_line';

type Position = {
  x: number;
  y: number;
};

type TopologyNode = {
  id: string;
  type: string;
  name?: string;
  position?: Position;
  params?: Record<string, unknown>;
  runtime_binding?: unknown;
  tags?: string[];
};

type TopologyEdge = {
  id: string;
  type: string;
  name?: string;
  from_node_id: string;
  to_node_id: string;
  params?: Record<string, unknown>;
};

type TopologyData = {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  economic_parameters: Record<string, unknown>;
};

type TopologyDraft = Omit<TopologyData, 'economic_parameters'> & {
  economic_parameters?: Record<string, unknown>;
};

type Selection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | null;

type NodeVisualSpec = {
  color: string;
  border: string;
  background: string;
  radius: number | string;
  width: number;
  height: number;
  clipPath?: string;
};

type LoadCategory = 'industrial' | 'commercial' | 'residential';

const LOAD_CATEGORY_VISUALS: Record<LoadCategory, NodeVisualSpec & { label: string }> = {
  industrial: {
    label: '工业',
    color: '#b45309',
    border: '#f59e0b',
    background: '#fffbeb',
    radius: '18px 18px 8px 8px',
    width: 128,
    height: 62,
  },
  commercial: {
    label: '商业',
    color: '#7c3aed',
    border: '#a78bfa',
    background: '#f5f3ff',
    radius: 14,
    width: 128,
    height: 62,
  },
  residential: {
    label: '居民',
    color: '#16a34a',
    border: '#86efac',
    background: '#f0fdf4',
    radius: '18px 18px 12px 12px',
    width: 128,
    height: 62,
  },
};

const EMPTY_TOPOLOGY_TEXT = `{
  "nodes": [],
  "edges": [],
  "economic_parameters": {}
}`;

const CANVAS_WIDTH = 2200;
const CANVAS_HEIGHT = 1400;
const TOPOLOGY_WORKBENCH_HEIGHT = 860;
const NODE_WIDTH = 128;
const NODE_HEIGHT = 64;
const DEFAULT_LINE_TYPE: EdgeKind = 'normal_line';
const DEFAULT_LINE_CODE = 'LC_MAIN';
const NODE_REPEL_PADDING = 10;
const LOAD_PANEL_REMOVED_PARAM_KEYS = [
  'description',
  'voltage_level_kv',
  'pv_capacity_kw',
  'grid_interconnection_limit_kw',
];

const LOAD_PANEL_READONLY_INFERRED_KEYS = [
  'search_power_min_kw',
  'search_duration_min_h',
  'search_duration_max_h',
  'device_power_max_kw',
] as const;

const LOAD_PANEL_INFERRED_KEY_LABELS: Record<(typeof LOAD_PANEL_READONLY_INFERRED_KEYS)[number], string> = {
  search_power_min_kw: 'GA 搜索功率下限 kW',
  search_duration_min_h: 'GA 搜索时长下限 h',
  search_duration_max_h: 'GA 搜索时长上限 h',
  device_power_max_kw: '设备功率上限 kW',
};

const TRANSFORMER_NODE_TYPES = new Set(['transformer', 'distribution_transformer']);
const BUS_EQUIPMENT_NODE_TYPES = new Set(['bus', 'ring_main_unit', 'branch', 'switch', 'breaker', 'fuse', 'regulator']);
const RESOURCE_NODE_TYPES = new Set(['pv', 'wind', 'storage']);
const NODE_ADVANCED_PARAM_KEYS: Record<string, readonly string[]> = {
  grid: ['base_kv', 'pu', 'phases', 'source_bus', 'dss_bus_name', 'mvasc3', 'mvasc1', 'x1r1', 'x0r0'],
  source: ['base_kv', 'pu', 'phases', 'source_bus', 'dss_bus_name', 'mvasc3', 'mvasc1', 'x1r1', 'x0r0'],
  transformer: [
    'rated_kva',
    'voltage_level_kv',
    'primary_voltage_kv',
    'primary_bus_name',
    'dss_bus_name',
    'secondary_bus_name',
    'primary_conn',
    'secondary_conn',
    'xhl_percent',
    'percent_r',
    'tap',
    'phases',
  ],
  distribution_transformer: [
    'enabled',
    'rated_kva',
    'primary_voltage_kv',
    'voltage_level_kv',
    'primary_bus_name',
    'dss_bus_name',
    'secondary_bus_name',
    'primary_conn',
    'secondary_conn',
    'xhl_percent',
    'percent_r',
    'tap',
    'phases',
  ],
  bus: ['dss_bus_name', 'voltage_level_kv', 'phases'],
  ring_main_unit: ['dss_bus_name', 'voltage_level_kv', 'phases'],
  branch: ['dss_bus_name', 'voltage_level_kv', 'phases'],
  switch: ['dss_name', 'enabled', 'normally_open', 'target_line'],
  breaker: ['dss_name', 'enabled', 'normally_open', 'target_line'],
  fuse: ['dss_name', 'enabled', 'normally_open', 'target_line', 'rated_current_a'],
  regulator: ['dss_name', 'enabled', 'target_transformer', 'winding', 'vreg', 'band', 'ptratio'],
  capacitor: ['dss_name', 'enabled', 'dss_bus_name', 'voltage_level_kv', 'phases', 'kvar', 'connection'],
  pv: ['dss_name', 'enabled', 'dss_bus_name', 'voltage_level_kv', 'phases', 'pmpp_kw', 'kva', 'pf', 'irradiance'],
  wind: ['dss_name', 'enabled', 'dss_bus_name', 'voltage_level_kv', 'phases', 'rated_kw', 'pf', 'model'],
  storage: [
    'dss_name',
    'enabled',
    'dss_bus_name',
    'voltage_level_kv',
    'phases',
    'rated_kw',
    'rated_kwh',
    'initial_soc_pct',
    'reserve_soc_pct',
  ],
  load: [
    'enabled',
    'node_id',
    'dss_bus_name',
    'dss_load_name',
    'target_kv_ln',
    'phases',
    'category',
    'remarks',
    'model_year',
    'design_kw',
    'kvar',
    'q_to_p_ratio',
    'connection',
    'model',
    'optimize_storage',
    'allow_grid_export',
    'transformer_capacity_kva',
    'transformer_pf_limit',
    'transformer_reserve_ratio',
    'dispatch_mode',
    'run_mode',
  ],
};
const NODE_HIDDEN_PERSISTED_PARAM_KEYS: Record<string, readonly string[]> = {
  distribution_transformer: ['transformer_role', 'is_distribution_transformer', 'role'],
  load: ['storage_placeholder', 'storage_placeholder_kw', 'storage_placeholder_kwh', 'storage_name'],
};
const EDGE_ADVANCED_PARAM_KEYS = [
  'linecode',
  'phases',
  'enabled',
  'normally_open',
  'length_km',
  'r_ohm_per_km',
  'x_ohm_per_km',
  'r0_ohm_per_km',
  'x0_ohm_per_km',
  'c1_nf_per_km',
  'c0_nf_per_km',
  'rated_current_a',
  'emerg_current_a',
] as const;

function isTransformerType(type: string) {
  return TRANSFORMER_NODE_TYPES.has(type);
}

function isBusEquipmentType(type: string) {
  return BUS_EQUIPMENT_NODE_TYPES.has(type);
}

function isResourceType(type: string) {
  return RESOURCE_NODE_TYPES.has(type);
}

const ECONOMIC_DEFAULT_PARAMS: Record<string, unknown> = {
  include_aux_service_revenue: false,
  include_demand_saving: true,
  include_capacity_revenue: false,
  include_loss_reduction_revenue: false,
  include_degradation_cost: true,
  include_government_subsidy: false,
  include_replacement_cost: true,
  default_capacity_price_yuan_per_kw: 0.05,
  default_delivery_price_yuan_per_kwh: 0.1,
  default_penalty_price_yuan_per_kwh: 0.2,
  default_activation_factor: 0.15,
  max_service_power_ratio: 0.3,
  capacity_service_price_yuan_per_kw_day: 0,
  capacity_revenue_eligible_days: 365,
  network_loss_price_yuan_per_kwh: 0.3,
  network_loss_proxy_rate: 0.02,
  government_subsidy_rate_on_capex: 0,
  government_subsidy_yuan_per_kwh: 0,
  government_subsidy_yuan_per_kw: 0,
  government_subsidy_cap_yuan: 0,
  project_life_years: 20,
  discount_rate: 0.06,
  annual_revenue_growth_rate: 0,
  annual_om_growth_rate: 0.02,
  power_related_capex_yuan_per_kw: 300,
  integration_markup_ratio: 0.15,
  safety_markup_ratio: 0.02,
  other_capex_yuan: 0,
  degradation_cost_yuan_per_kwh_throughput: 0.03,
  battery_capex_share: 0.6,
  cycle_life_efc: 8000,
  annual_cycle_limit: 0,
  calendar_life_years: 20,
  calendar_fade_share: 0.15,
  min_degradation_cost_ratio: 0,
  replacement_cost_ratio: 0.6,
  replacement_year_override: 0,
  replacement_trigger_soh: 0.7,
  replacement_reset_soh: 0.95,
  annual_fixed_om_yuan_per_kw_year: 18,
  annual_variable_om_yuan_per_kwh: 0.004,
  demand_charge_yuan_per_kw_month: 48,
  daily_demand_shadow_yuan_per_kw: 48,
  voltage_penalty_coeff_yuan: 0,
};

const ECONOMIC_PARAM_KEYS = new Set(Object.keys(ECONOMIC_DEFAULT_PARAMS));

const LINE_CODE_OPTIONS = [
  {
    value: 'LC_MAIN',
    label: '10kV主干线',
    r_ohm_per_km: 0.251742424,
    x_ohm_per_km: 0.255208333,
    r0_ohm_per_km: 0.251742424,
    x0_ohm_per_km: 0.255208333,
    c1_nf_per_km: 2.270366128,
    c0_nf_per_km: 2.270366128,
    rated_current_a: 1200,
    emerg_current_a: 1500,
  },
  {
    value: 'LC_BRANCH',
    label: '10kV分支线',
    r_ohm_per_km: 0.363958,
    x_ohm_per_km: 0.269167,
    r0_ohm_per_km: 0.363958,
    x0_ohm_per_km: 0.269167,
    c1_nf_per_km: 2.1922,
    c0_nf_per_km: 2.1922,
    rated_current_a: 800,
    emerg_current_a: 1000,
  },
  {
    value: 'LC_CABLE',
    label: '10kV电缆/大载流线路',
    r_ohm_per_km: 0.254261364,
    x_ohm_per_km: 0.097045455,
    r0_ohm_per_km: 0.254261364,
    x0_ohm_per_km: 0.097045455,
    c1_nf_per_km: 44.70661522,
    c0_nf_per_km: 44.70661522,
    rated_current_a: 1400,
    emerg_current_a: 1700,
  },
  {
    value: 'LC_LIGHT',
    label: '末端轻载支线',
    r_ohm_per_km: 0.530208,
    x_ohm_per_km: 0.281345,
    r0_ohm_per_km: 0.530208,
    x0_ohm_per_km: 0.281345,
    c1_nf_per_km: 2.12257,
    c0_nf_per_km: 2.12257,
    rated_current_a: 300,
    emerg_current_a: 450,
  },
];

const LINE_STROKE_BY_CODE: Record<string, string> = {
  LC_MAIN: '#1d4ed8',
  LC_BRANCH: '#0f766e',
  LC_CABLE: '#2563eb',
  LC_LIGHT: '#64748b',
};

const SERVICE_LINE_LINECODE = 'LC_CABLE';
const SERVICE_LINE_DEFAULT_LENGTH_KM = 0.005;
const SERVICE_LINE_RESOURCE_MARGIN = 1.1;
const SERVICE_LINE_EMERGENCY_MARGIN = 1.2;
const SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN = 1.25;
const SERVICE_LINE_MIN_RATED_A = 1;

// OpenDSS 8500Bus/WireData.dss — 铜缆参数，用于接户线并联等效计算（与 dss_builder_service.py 保持一致）
const WIRE_DATA_CU: Array<{name: string; rac: number; normamps: number}> = [
  { name: '250_CU',  rac: 0.159692, normamps: 540  },
  { name: '350_CU',  rac: 0.114643, normamps: 660  },
  { name: '400_CU',  rac: 0.100662, normamps: 730  },
  { name: '500_CU',  rac: 0.080778, normamps: 840  },
  { name: '600_CU',  rac: 0.062323, normamps: 900  },
  { name: '750_CU',  rac: 0.055302, normamps: 1090 },
  { name: '1000_CU', rac: 0.042875, normamps: 1300 },
];
const WIRE_XR_RATIO = 0.46; // 50 Hz 铜缆典型 X/R
const SERVICE_LINE_LOW_Z_CURRENT_THRESHOLD_A = 1500.0;

type DistributionServiceEdgeProfile = {
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

const LINE_LEGEND_ITEMS: Array<{ label: string; stroke: string; dash?: string }> = [
  { label: '用户低压接入线（自动）', stroke: '#d97706' },
  { label: '常开联络线', stroke: '#7c3aed', dash: '8 6' },
  { label: '10kV主干线', stroke: LINE_STROKE_BY_CODE.LC_MAIN },
  { label: '10kV分支线', stroke: LINE_STROKE_BY_CODE.LC_BRANCH },
  { label: '10kV电缆/大载流线路', stroke: LINE_STROKE_BY_CODE.LC_CABLE },
  { label: '末端轻载支线', stroke: LINE_STROKE_BY_CODE.LC_LIGHT },
];

function lineCodeDefaults(linecode: string) {
  return LINE_CODE_OPTIONS.find((item) => item.value === linecode) ?? LINE_CODE_OPTIONS[0];
}

type Ieee33Load = {
  nodeId: number;
  kw: number;
  kvar: number;
};

type Ieee33Line = {
  id: string;
  from: string;
  to: string;
  lengthKm: number;
  linecode: string;
  normamps: number;
  emergamps: number;
};

const IEEE33_LOADS: Ieee33Load[] = [
  { nodeId: 1, kw: 802, kvar: 200.5 },
  { nodeId: 2, kw: 774, kvar: 232.2 },
  { nodeId: 3, kw: 375, kvar: 112.5 },
  { nodeId: 4, kw: 284, kvar: 99.4 },
  { nodeId: 5, kw: 186, kvar: 65.1 },
  { nodeId: 6, kw: 1022, kvar: 255.5 },
  { nodeId: 7, kw: 858, kvar: 214.5 },
  { nodeId: 8, kw: 1486, kvar: 371.5 },
  { nodeId: 9, kw: 3098, kvar: 619.6 },
  { nodeId: 10, kw: 106, kvar: 37.1 },
  { nodeId: 11, kw: 175, kvar: 61.25 },
  { nodeId: 12, kw: 344, kvar: 103.2 },
  { nodeId: 13, kw: 548, kvar: 164.4 },
  { nodeId: 14, kw: 546, kvar: 163.8 },
  { nodeId: 15, kw: 18, kvar: 6.3 },
  { nodeId: 16, kw: 350, kvar: 105 },
  { nodeId: 17, kw: 214, kvar: 74.9 },
  { nodeId: 18, kw: 136, kvar: 47.6 },
  { nodeId: 19, kw: 804, kvar: 201 },
  { nodeId: 20, kw: 3112, kvar: 622.4 },
  { nodeId: 21, kw: 1173, kvar: 293.25 },
  { nodeId: 22, kw: 394, kvar: 118.2 },
  { nodeId: 23, kw: 380, kvar: 106.4 },
  { nodeId: 24, kw: 36, kvar: 9 },
  { nodeId: 25, kw: 404, kvar: 113.12 },
  { nodeId: 26, kw: 2903, kvar: 870.9 },
  { nodeId: 27, kw: 138, kvar: 41.4 },
  { nodeId: 28, kw: 350, kvar: 98 },
  { nodeId: 29, kw: 145, kvar: 43.5 },
  { nodeId: 30, kw: 54, kvar: 9.72 },
  { nodeId: 31, kw: 66, kvar: 11.88 },
  { nodeId: 32, kw: 42, kvar: 7.56 },
  { nodeId: 33, kw: 47, kvar: 8.46 },
];

const IEEE33_LINES: Ieee33Line[] = [
  { id: 'F01_0_J1', from: 'n0', to: 'f01_j1', lengthKm: 0.35, linecode: 'LC_CABLE', normamps: 1400, emergamps: 1700 },
  { id: 'F01_J1_20', from: 'f01_j1', to: 'n20', lengthKm: 0.3, linecode: 'LC_MAIN', normamps: 1200, emergamps: 1500 },
  { id: 'F01_20_01', from: 'n20', to: 'n1', lengthKm: 0.18, linecode: 'LC_BRANCH', normamps: 800, emergamps: 1000 },
  { id: 'F01_J1_11', from: 'f01_j1', to: 'n11', lengthKm: 0.22, linecode: 'LC_LIGHT', normamps: 500, emergamps: 700 },
  { id: 'F01_J1_04', from: 'f01_j1', to: 'n4', lengthKm: 0.2, linecode: 'LC_BRANCH', normamps: 600, emergamps: 800 },
  { id: 'F02_0_13', from: 'n0', to: 'n13', lengthKm: 0.4, linecode: 'LC_CABLE', normamps: 1400, emergamps: 1700 },
  { id: 'F02_13_02', from: 'n13', to: 'n2', lengthKm: 0.22, linecode: 'LC_MAIN', normamps: 1200, emergamps: 1500 },
  { id: 'F02_02_06', from: 'n2', to: 'n6', lengthKm: 0.28, linecode: 'LC_BRANCH', normamps: 900, emergamps: 1100 },
  { id: 'F03_0_03', from: 'n0', to: 'n3', lengthKm: 0.32, linecode: 'LC_CABLE', normamps: 900, emergamps: 1100 },
  { id: 'F03_03_15', from: 'n3', to: 'n15', lengthKm: 0.15, linecode: 'LC_LIGHT', normamps: 300, emergamps: 450 },
  { id: 'F04_0_08', from: 'n0', to: 'n8', lengthKm: 0.42, linecode: 'LC_CABLE', normamps: 1200, emergamps: 1500 },
  { id: 'F04_08_32', from: 'n8', to: 'n32', lengthKm: 0.18, linecode: 'LC_LIGHT', normamps: 300, emergamps: 450 },
  { id: 'F05_0_09', from: 'n0', to: 'n9', lengthKm: 0.55, linecode: 'LC_CABLE', normamps: 1500, emergamps: 1800 },
  { id: 'F06_0_10', from: 'n0', to: 'n10', lengthKm: 0.3, linecode: 'LC_MAIN', normamps: 500, emergamps: 700 },
  { id: 'F06_10_05', from: 'n10', to: 'n5', lengthKm: 0.2, linecode: 'LC_BRANCH', normamps: 450, emergamps: 650 },
  { id: 'F07_0_J1', from: 'n0', to: 'f07_j1', lengthKm: 0.38, linecode: 'LC_CABLE', normamps: 1000, emergamps: 1300 },
  { id: 'F07_J1_16', from: 'f07_j1', to: 'n16', lengthKm: 0.2, linecode: 'LC_MAIN', normamps: 700, emergamps: 900 },
  { id: 'F07_16_18', from: 'n16', to: 'n18', lengthKm: 0.15, linecode: 'LC_BRANCH', normamps: 500, emergamps: 700 },
  { id: 'F07_18_17', from: 'n18', to: 'n17', lengthKm: 0.18, linecode: 'LC_BRANCH', normamps: 450, emergamps: 650 },
  { id: 'F07_J1_24', from: 'f07_j1', to: 'n24', lengthKm: 0.12, linecode: 'LC_LIGHT', normamps: 300, emergamps: 450 },
  { id: 'F07_24_14', from: 'n24', to: 'n14', lengthKm: 0.2, linecode: 'LC_BRANCH', normamps: 600, emergamps: 800 },
  { id: 'F07_J1_22', from: 'f07_j1', to: 'n22', lengthKm: 0.16, linecode: 'LC_BRANCH', normamps: 500, emergamps: 700 },
  { id: 'F08_0_J1', from: 'n0', to: 'f08_j1', lengthKm: 0.36, linecode: 'LC_CABLE', normamps: 1000, emergamps: 1300 },
  { id: 'F08_J1_25', from: 'f08_j1', to: 'n25', lengthKm: 0.14, linecode: 'LC_BRANCH', normamps: 500, emergamps: 700 },
  { id: 'F08_J1_21', from: 'f08_j1', to: 'n21', lengthKm: 0.18, linecode: 'LC_MAIN', normamps: 900, emergamps: 1100 },
  { id: 'F08_21_12', from: 'n21', to: 'n12', lengthKm: 0.16, linecode: 'LC_BRANCH', normamps: 500, emergamps: 700 },
  { id: 'F09_0_19', from: 'n0', to: 'n19', lengthKm: 0.28, linecode: 'LC_MAIN', normamps: 800, emergamps: 1000 },
  { id: 'F10_0_07', from: 'n0', to: 'n7', lengthKm: 0.3, linecode: 'LC_MAIN', normamps: 900, emergamps: 1100 },
  { id: 'F11_0_23', from: 'n0', to: 'n23', lengthKm: 0.25, linecode: 'LC_MAIN', normamps: 600, emergamps: 800 },
  { id: 'F12_0_26', from: 'n0', to: 'n26', lengthKm: 0.42, linecode: 'LC_CABLE', normamps: 1200, emergamps: 1500 },
  { id: 'F13_0_J1', from: 'n0', to: 'f13_j1', lengthKm: 0.32, linecode: 'LC_CABLE', normamps: 700, emergamps: 900 },
  { id: 'F13_J1_27', from: 'f13_j1', to: 'n27', lengthKm: 0.12, linecode: 'LC_BRANCH', normamps: 450, emergamps: 650 },
  { id: 'F13_27_29', from: 'n27', to: 'n29', lengthKm: 0.14, linecode: 'LC_BRANCH', normamps: 450, emergamps: 650 },
  { id: 'F13_29_30', from: 'n29', to: 'n30', lengthKm: 0.12, linecode: 'LC_LIGHT', normamps: 300, emergamps: 450 },
  { id: 'F13_30_31', from: 'n30', to: 'n31', lengthKm: 0.12, linecode: 'LC_LIGHT', normamps: 300, emergamps: 450 },
  { id: 'F13_J1_28', from: 'f13_j1', to: 'n28', lengthKm: 0.1, linecode: 'LC_BRANCH', normamps: 400, emergamps: 600 },
  { id: 'F13_J1_33', from: 'f13_j1', to: 'n33', lengthKm: 0.1, linecode: 'LC_LIGHT', normamps: 250, emergamps: 400 },
];

const IEEE33_BRANCH_BUSES = ['f01_j1', 'f07_j1', 'f08_j1', 'f13_j1'];

const IEEE33_BUS_POSITIONS: Record<string, Position> = {
  sourcebus: { x: 60, y: 500 },
  n0: { x: 240, y: 500 },
  f01_j1: { x: 430, y: 80 },
  n20: { x: 600, y: 50 },
  n1: { x: 760, y: 50 },
  n11: { x: 600, y: 95 },
  n4: { x: 600, y: 140 },
  n13: { x: 430, y: 180 },
  n2: { x: 590, y: 180 },
  n6: { x: 750, y: 180 },
  n3: { x: 430, y: 260 },
  n15: { x: 590, y: 260 },
  n8: { x: 430, y: 340 },
  n32: { x: 590, y: 340 },
  n9: { x: 520, y: 420 },
  n10: { x: 430, y: 500 },
  n5: { x: 590, y: 500 },
  f07_j1: { x: 430, y: 590 },
  n16: { x: 580, y: 545 },
  n18: { x: 730, y: 545 },
  n17: { x: 880, y: 545 },
  n24: { x: 580, y: 595 },
  n14: { x: 730, y: 595 },
  n22: { x: 580, y: 645 },
  f08_j1: { x: 430, y: 720 },
  n25: { x: 580, y: 690 },
  n21: { x: 580, y: 745 },
  n12: { x: 730, y: 745 },
  n19: { x: 430, y: 820 },
  n7: { x: 430, y: 900 },
  n23: { x: 430, y: 980 },
  n26: { x: 620, y: 1020 },
  f13_j1: { x: 980, y: 850 },
  n27: { x: 1140, y: 800 },
  n29: { x: 1300, y: 800 },
  n30: { x: 1460, y: 800 },
  n31: { x: 1620, y: 800 },
  n28: { x: 1140, y: 870 },
  n33: { x: 1140, y: 940 },
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function safeNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function stringParam(params: Record<string, unknown> | undefined, key: string, fallback: string) {
  const value = params?.[key];
  return typeof value === 'string' ? value : String(value ?? fallback);
}

function numberParam(params: Record<string, unknown> | undefined, key: string, fallback: number) {
  const value = Number(params?.[key] ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function numberInputValue(params: Record<string, unknown> | undefined, key: string) {
  const value = params?.[key];
  if (value === null || value === undefined || value === '') return '';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : '';
}

function roundParamNumber(value: number, digits = 6) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function derivePowerFactorFromRatio(ratio: number) {
  if (!(Number.isFinite(ratio) && ratio >= 0)) return null;
  return 1 / Math.sqrt(1 + ratio * ratio);
}

function getLoadReactiveRatio(params: Record<string, unknown> | undefined) {
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

function getLoadPowerFactor(params: Record<string, unknown> | undefined) {
  const ratio = getLoadReactiveRatio(params);
  return ratio == null ? null : derivePowerFactorFromRatio(ratio);
}

function syncLoadElectricalParams(params: Record<string, unknown>) {
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

function cleanLoadPanelParams(params: Record<string, unknown> | undefined) {
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

function pickParamKeys(
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

function editableNodeParams(node: TopologyNode | null | undefined) {
  if (!node) return {};
  const displayType = getDisplayNodeType(node);
  const params = node.type === 'load' ? cleanLoadPanelParams(node.params) : { ...(node.params ?? {}) };
  const keys = NODE_ADVANCED_PARAM_KEYS[displayType] ?? [];
  return pickParamKeys(params, keys);
}

function getHiddenNodeParams(node: TopologyNode) {
  const displayType = getDisplayNodeType(node);
  const hiddenKeys = NODE_HIDDEN_PERSISTED_PARAM_KEYS[displayType] ?? [];
  return pickParamKeys(node.params, hiddenKeys);
}

function sanitizeNodeParamsForEditor(node: TopologyNode, params: Record<string, unknown>) {
  const displayType = getDisplayNodeType(node);
  const cleaned = node.type === 'load' ? cleanLoadPanelParams(params) : { ...params };
  const editable = pickParamKeys(cleaned, NODE_ADVANCED_PARAM_KEYS[displayType] ?? []);
  return {
    ...getHiddenNodeParams(node),
    ...editable,
  };
}

function editableEdgeParams(edge: TopologyEdge | null | undefined) {
  if (!edge) return {};
  return pickParamKeys(edge.params, EDGE_ADVANCED_PARAM_KEYS);
}

function hasPositiveNumberParam(params: Record<string, unknown> | undefined, key: string) {
  const value = params?.[key];
  if (value === null || value === undefined || value === '') return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

function booleanParam(params: Record<string, unknown> | undefined, key: string, fallback: boolean) {
  const value = params?.[key];
  return legacyBool(value, fallback);
}

function isDistributionTransformerNode(node: Pick<TopologyNode, 'type' | 'params'> | null | undefined) {
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

function isLowSideResourceNode(node: Pick<TopologyNode, 'type'> | null | undefined) {
  if (!node) return false;
  return ['load', 'storage', 'pv', 'wind', 'capacitor'].includes(node.type);
}

function getDistributionServiceEdgeNodes(
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

function threePhaseCurrentFromKva(kva: number, kvLl: number) {
  if (kva <= 0 || kvLl <= 0) return 0;
  return kva / (Math.sqrt(3) * kvLl);
}

function buildDistributionServiceEdgeProfile(
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

function resourceApparentPowerKva(node: TopologyNode) {
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

function getDistributionServiceEdgeProfile(
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

function edgeLineCodeLabel(linecode: string) {
  return lineCodeDefaults(linecode).label;
}

function edgeVisualMeta(edge: TopologyEdge, nodeMap: Map<string, TopologyNode>) {
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

function formatCurrentDisplay(currentA: number) {
  if (!Number.isFinite(currentA) || currentA <= 0) return '--';
  if (currentA >= 1000) return `${(currentA / 1000).toFixed(currentA >= 10000 ? 1 : 2)} kA`;
  return `${Math.round(currentA)} A`;
}

function getDisplayNodeType(node: Pick<TopologyNode, 'type' | 'params'>) {
  return isDistributionTransformerNode(node) ? 'distribution_transformer' : node.type;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stripEconomicParams(params: Record<string, unknown>) {
  const next = { ...params };
  ECONOMIC_PARAM_KEYS.forEach((key) => {
    delete next[key];
  });
  return next;
}

function legacyBool(value: unknown, fallback: boolean) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const text = value.trim().toLowerCase();
    if (['1', 'true', 'yes', 'on', '是', '启用'].includes(text)) return true;
    if (['0', 'false', 'no', 'off', '否', '停用'].includes(text)) return false;
  }
  return fallback;
}

function collectLegacyEconomicParams(node: Partial<TopologyNode>) {
  const params = isRecord(node.params) ? node.params : {};
  const migrated: Record<string, unknown> = {};
  ECONOMIC_PARAM_KEYS.forEach((key) => {
    if (params[key] !== undefined) migrated[key] = params[key];
  });
  return migrated;
}

function extractLegacyEconomicParams(nodes: Partial<TopologyNode>[]) {
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

function normalizeEconomicParams(input: unknown, legacy: Record<string, unknown> = {}) {
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

function stringifyEconomicParams(input: unknown) {
  return JSON.stringify(normalizeEconomicParams(input));
}

function normalizeNode(node: Partial<TopologyNode>, index: number): TopologyNode {
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

function normalizeEdge(edge: Partial<TopologyEdge>, index: number): TopologyEdge {
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

function normalizeTopology(input: unknown): TopologyData {
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

function stringifyTopology(data: TopologyData) {
  return JSON.stringify(data, null, 2);
}

function getLoadCategory(value: unknown): LoadCategory {
  const text = String(value ?? '').trim().toLowerCase();
  if (text === 'commercial' || text === '商业') return 'commercial';
  if (text === 'residential' || text === '居民') return 'residential';
  return 'industrial';
}

function getLoadCategoryVisual(value: unknown) {
  return LOAD_CATEGORY_VISUALS[getLoadCategory(value)];
}

function getNodeVisual(type: string): NodeVisualSpec {
  switch (type) {
    case 'grid':
    case 'source':
      return {
        color: '#dc2626',
        border: '#f87171',
        background: '#fff1f2',
        radius: 999,
        width: 126,
        height: 58,
      };
    case 'transformer':
      return {
        color: '#d97706',
        border: '#f59e0b',
        background: '#fffbeb',
        radius: 16,
        width: 128,
        height: 64,
      };
    case 'distribution_transformer':
      return {
        color: '#a16207',
        border: '#facc15',
        background: '#fefce8',
        radius: 14,
        width: 128,
        height: 64,
      };
    case 'bus':
      return {
        color: '#2563eb',
        border: '#60a5fa',
        background: '#eff6ff',
        radius: 999,
        width: 138,
        height: 44,
      };
    case 'ring_main_unit':
      return {
        color: '#475569',
        border: '#94a3b8',
        background: '#f8fafc',
        radius: 12,
        width: 126,
        height: 62,
        clipPath: 'polygon(10px 0, calc(100% - 10px) 0, 100% 10px, 100% calc(100% - 10px), calc(100% - 10px) 100%, 10px 100%, 0 calc(100% - 10px), 0 10px)',
      };
    case 'branch':
      return {
        color: '#0f766e',
        border: '#2dd4bf',
        background: '#ecfdf5',
        radius: 999,
        width: 70,
        height: 70,
      };
    case 'switch':
      return {
        color: '#334155',
        border: '#94a3b8',
        background: '#f8fafc',
        radius: 10,
        width: 104,
        height: 54,
      };
    case 'breaker':
      return {
        color: '#991b1b',
        border: '#fca5a5',
        background: '#fef2f2',
        radius: 10,
        width: 104,
        height: 54,
      };
    case 'fuse':
      return {
        color: '#9333ea',
        border: '#c4b5fd',
        background: '#faf5ff',
        radius: 10,
        width: 104,
        height: 54,
      };
    case 'regulator':
      return {
        color: '#0369a1',
        border: '#7dd3fc',
        background: '#f0f9ff',
        radius: 12,
        width: 118,
        height: 58,
      };
    case 'capacitor':
      return {
        color: '#0284c7',
        border: '#38bdf8',
        background: '#f0f9ff',
        radius: 999,
        width: 86,
        height: 56,
      };
    case 'pv':
      return {
        color: '#2563eb',
        border: '#93c5fd',
        background: '#eff6ff',
        radius: 12,
        width: 112,
        height: 60,
      };
    case 'wind':
      return {
        color: '#0f766e',
        border: '#5eead4',
        background: '#ecfdf5',
        radius: 999,
        width: 92,
        height: 60,
      };
    case 'storage':
      return {
        color: '#475569',
        border: '#94a3b8',
        background: '#f8fafc',
        radius: 12,
        width: 112,
        height: 60,
      };
    case 'load':
      return {
        color: '#059669',
        border: '#34d399',
        background: '#f0fdf4',
        radius: '18px 18px 8px 8px',
        width: 128,
        height: 62,
      };
    default:
      return {
        color: '#64748b',
        border: '#cbd5e1',
        background: '#ffffff',
        radius: 12,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      };
  }
}

function getNodeVisualForNode(node: TopologyNode): NodeVisualSpec {
  if (node.type === 'load') return getLoadCategoryVisual(node.params?.category);
  return getNodeVisual(getDisplayNodeType(node));
}

function getNodeSize(type: string) {
  const visual = getNodeVisual(type);
  return { width: visual.width, height: visual.height };
}

function getNodeSizeForNode(node: TopologyNode) {
  const visual = getNodeVisualForNode(node);
  return { width: visual.width, height: visual.height };
}

function getNodeAnchorShape(node: TopologyNode) {
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

function getNodeCenter(node: TopologyNode) {
  const size = getNodeSizeForNode(node);
  return {
    x: safeNumber(node.position?.x, 100) + size.width / 2,
    y: safeNumber(node.position?.y, 100) + size.height / 2,
  };
}

function getNodeBoundaryPoint(node: TopologyNode, toward: { x: number; y: number }) {
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
    return {
      x: boundaryX + dx * push,
      y: boundaryY + dy * push,
    };
  }

  const halfWidth = Math.max(1, size.width / 2 - 2);
  const halfHeight = Math.max(1, size.height / 2 - 2);
  const xScale = Math.abs(dx) > 0.001 ? halfWidth / Math.abs(dx) : Number.POSITIVE_INFINITY;
  const yScale = Math.abs(dy) > 0.001 ? halfHeight / Math.abs(dy) : Number.POSITIVE_INFINITY;
  const scale = Math.min(xScale, yScale, 1);
  const push = distance > 0.001 ? overshoot / distance : 0;
  return {
    x: center.x + dx * (scale + push),
    y: center.y + dy * (scale + push),
  };
}

function resolveNodeOverlaps(nodes: TopologyNode[], lockedNodeId?: string) {
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

function getNodeLabel(type: string) {
  switch (type) {
    case 'grid':
      return '电网/电源';
    case 'source':
      return '电源';
    case 'transformer':
      return '主变';
    case 'distribution_transformer':
      return '用户配变';
    case 'bus':
      return '母线';
    case 'ring_main_unit':
      return '环网柜';
    case 'branch':
      return '分支点';
    case 'switch':
      return '开关';
    case 'breaker':
      return '断路器';
    case 'fuse':
      return '熔断器';
    case 'regulator':
      return '电压调节';
    case 'capacitor':
      return '电容器';
    case 'pv':
      return '光伏';
    case 'wind':
      return '风机';
    case 'storage':
      return '储能';
    case 'load':
      return '负荷';
    default:
      return type;
  }
}

function getNodeLabelForNode(node: Pick<TopologyNode, 'type' | 'params'>) {
  return getNodeLabel(getDisplayNodeType(node));
}

function getLoadNodeCode(node: TopologyNode) {
  const params = node.params ?? {};
  const dssLoadName = stringParam(params, 'dss_load_name', '').trim();
  if (dssLoadName) return dssLoadName;

  const nodeId = numberParam(params, 'node_id', 0);
  if (nodeId > 0) return `LD${String(Math.round(nodeId)).padStart(2, '0')}`;

  const fallbackName = String(node.name ?? node.id).trim();
  return fallbackName || node.id;
}

function getNodeDetail(node: TopologyNode) {
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
    case 'bus': {
      const kv = numberParam(params, 'voltage_level_kv', 10);
      return `${kv} kV 母线`;
    }
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

function buildNodeDefaultParams(type: NodeKind) {
  switch (type) {
    case 'grid':
      return {
        base_kv: 110,
        pu: 1.0,
        phases: 3,
        source_bus: 'sourcebus',
        mvasc3: 1000,
        mvasc1: 1000,
        x1r1: 10,
        x0r0: 3,
      };
    case 'transformer':
      return {
        rated_kva: 31500,
        voltage_level_kv: 10,
        primary_voltage_kv: 110,
        primary_bus_name: 'sourcebus',
        dss_bus_name: 'n0',
        primary_conn: 'wye',
        secondary_conn: 'wye',
        xhl_percent: 7,
        percent_r: 0.5,
        tap: 1,
        phases: 3,
      };
    case 'distribution_transformer':
      return {
        enabled: true,
        rated_kva: 1000,
        primary_voltage_kv: 10,
        voltage_level_kv: 0.4,
        primary_bus_name: '',
        dss_bus_name: '',
        secondary_bus_name: '',
        primary_conn: 'delta',
        secondary_conn: 'wye',
        xhl_percent: 6,
        percent_r: 1,
        tap: 1,
        phases: 3,
      };
    case 'bus':
      return {
        voltage_level_kv: 10,
        dss_bus_name: '',
        phases: 3,
      };
    case 'ring_main_unit':
      return {
        voltage_level_kv: 10,
        dss_bus_name: '',
        phases: 3,
      };
    case 'branch':
      return {
        dss_bus_name: '',
        voltage_level_kv: 10,
        phases: 3,
      };
    case 'switch':
      return {
        enabled: true,
        normally_open: false,
        dss_bus_name: '',
        voltage_level_kv: 10,
        target_line: '',
        phases: 3,
      };
    case 'breaker':
      return {
        enabled: true,
        normally_open: false,
        dss_bus_name: '',
        voltage_level_kv: 10,
        target_line: '',
        phases: 3,
      };
    case 'fuse':
      return {
        enabled: true,
        normally_open: false,
        dss_bus_name: '',
        voltage_level_kv: 10,
        target_line: '',
        rated_current_a: 200,
        phases: 3,
      };
    case 'regulator':
      return {
        enabled: true,
        dss_bus_name: '',
        voltage_level_kv: 10,
        target_transformer: '',
        winding: 2,
        vreg: 120,
        band: 2,
        ptratio: 60,
        phases: 3,
      };
    case 'capacitor':
      return {
        enabled: true,
        dss_bus_name: '',
        voltage_level_kv: 10,
        kvar: 300,
        connection: 'wye',
        phases: 3,
      };
    case 'pv':
      return {
        enabled: true,
        dss_bus_name: '',
        dss_name: '',
        voltage_level_kv: 0.4,
        pmpp_kw: 100,
        kva: 110,
        pf: 1,
        irradiance: 1,
        phases: 3,
      };
    case 'wind':
      return {
        enabled: true,
        dss_bus_name: '',
        dss_name: '',
        voltage_level_kv: 0.4,
        rated_kw: 100,
        pf: 0.98,
        phases: 3,
      };
    case 'storage':
      return {
        enabled: true,
        dss_bus_name: '',
        dss_name: '',
        voltage_level_kv: 0.4,
        rated_kw: 100,
        rated_kwh: 215,
        initial_soc_pct: 50,
        reserve_soc_pct: 10,
        phases: 3,
      };
    case 'load':
      return {
        enabled: true,
        node_id: null,
        dss_bus_name: '',
        dss_load_name: '',
        target_kv_ln: null,
        phases: 3,
        category: 'industrial',
        remarks: '',
        model_year: 2025,
        q_to_p_ratio: 0.25,
        pf: 0.95,
        optimize_storage: true,
        allow_grid_export: false,
        transformer_capacity_kva: 1000,
        transformer_pf_limit: 0.95,
        transformer_reserve_ratio: 0.15,
        dispatch_mode: 'hybrid',
        run_mode: 'single_user',
      };
    default:
      return {};
  }
}

function phaseSuffix(phases: number) {
  return phases === 1 ? '.1' : '.1.2.3';
}

function dssSafeName(value: string) {
  return value.replace(/[^A-Za-z0-9_]/g, '_').replace(/^_+|_+$/g, '') || 'unnamed';
}

function nodeDssBusName(node: TopologyNode) {
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

function nodeDssLoadName(node: TopologyNode) {
  const params = node.params ?? {};
  const explicit = stringParam(params, 'dss_load_name', '').trim() || stringParam(params, 'load_name', '').trim();
  if (explicit) return dssSafeName(explicit);
  const nodeId = numberParam(params, 'node_id', 0);
  return nodeId > 0 ? `LD${String(nodeId).padStart(2, '0')}` : dssSafeName(node.id);
}

function buildDssPreview(topology: TopologyData) {
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

function ieee33BusNodeId(bus: string) {
  if (bus === 'sourcebus') return 'source_grid';
  if (bus === 'n0') return 'tx_main';
  if (bus.startsWith('f')) return `branch_${bus}`;
  if (bus.startsWith('n')) return `bus_${bus.slice(1).padStart(2, '0')}`;
  return dssSafeName(bus);
}

function ieee33Position(bus: string) {
  return IEEE33_BUS_POSITIONS[bus] ?? { x: 120, y: 120 };
}

function ieee33LoadNodeId(nodeId: number) {
  return `load_${String(nodeId).padStart(2, '0')}`;
}

function ieee33CustomerTransformerNodeId(nodeId: number) {
  return `user_tx_${String(nodeId).padStart(2, '0')}`;
}

function ieee33LoadCategory(nodeId: number): LoadCategory {
  if (nodeId >= 23 && nodeId <= 29) return 'commercial';
  if (nodeId >= 30) return 'residential';
  return 'industrial';
}

function standardCustomerTransformerKva(kw: number) {
  const requiredKva = kw / 0.8;
  const standards = [100, 160, 250, 400, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300];
  return standards.find((kva) => kva >= requiredKva) ?? Math.ceil(requiredKva / 1000) * 1000;
}

function ieee33CustomerTransformerPosition(nodeId: number) {
  const base = ieee33Position(`n${nodeId}`);
  return { x: base.x + 150, y: base.y - 10 };
}

function ieee33LoadPosition(nodeId: number) {
  const base = ieee33Position(`n${nodeId}`);
  return { x: base.x + 292, y: base.y - 10 };
}

function lineParams(linecode: string, lengthKm: number, ratedCurrentA?: number, emergCurrentA?: number) {
  const defaults = lineCodeDefaults(linecode);
  return {
    length_km: lengthKm,
    linecode: defaults.value,
    r_ohm_per_km: defaults.r_ohm_per_km,
    x_ohm_per_km: defaults.x_ohm_per_km,
    r0_ohm_per_km: defaults.r0_ohm_per_km,
    x0_ohm_per_km: defaults.x0_ohm_per_km,
    c1_nf_per_km: defaults.c1_nf_per_km,
    c0_nf_per_km: defaults.c0_nf_per_km,
    rated_current_a: ratedCurrentA ?? defaults.rated_current_a,
    emerg_current_a: emergCurrentA ?? defaults.emerg_current_a,
    enabled: true,
    normally_open: false,
    phases: 3,
  };
}

function buildIeee33Template(): TopologyData {
  const nodes: TopologyNode[] = [
    {
      id: 'source_grid',
      type: 'grid',
      name: '上级电网 sourcebus',
      position: ieee33Position('sourcebus'),
      params: {
        base_kv: 110,
        pu: 1,
        phases: 3,
        source_bus: 'sourcebus',
        mvasc3: 1000,
        mvasc1: 1000,
        x1r1: 10,
        x0r0: 3,
      },
      runtime_binding: null,
      tags: ['ieee33-template'],
    },
    {
      id: 'tx_main',
      type: 'transformer',
      name: '主变 n0',
      position: ieee33Position('n0'),
      params: {
        rated_kva: 31500,
        voltage_level_kv: 10,
        primary_voltage_kv: 110,
        primary_bus_name: 'sourcebus',
        dss_bus_name: 'n0',
        secondary_bus_name: 'n0',
        primary_conn: 'wye',
        secondary_conn: 'wye',
        xhl_percent: 7,
        percent_r: 0.5,
        tap: 1,
        phases: 3,
      },
      runtime_binding: null,
      tags: ['ieee33-template'],
    },
    ...IEEE33_BRANCH_BUSES.map<TopologyNode>((bus) => ({
      id: ieee33BusNodeId(bus),
      type: 'branch',
      name: `分支点 ${bus}`,
      position: ieee33Position(bus),
      params: {
        dss_bus_name: bus,
        voltage_level_kv: 10,
        phases: 3,
      },
      runtime_binding: null,
      tags: ['ieee33-template'],
    })),
    ...IEEE33_LOADS.map<TopologyNode>((load) => ({
      id: ieee33BusNodeId(`n${load.nodeId}`),
      type: 'bus',
      name: `10kV接入点 n${load.nodeId}`,
      position: ieee33Position(`n${load.nodeId}`),
      params: {
        dss_bus_name: `n${load.nodeId}`,
        voltage_level_kv: 10,
        phases: 3,
      },
      runtime_binding: null,
      tags: ['ieee33-template'],
    })),
    ...IEEE33_LOADS.map<TopologyNode>((load) => {
      const transformerKva = standardCustomerTransformerKva(load.kw);
      return {
        id: ieee33CustomerTransformerNodeId(load.nodeId),
        type: 'transformer',
        name: `用户配变 LD${String(load.nodeId).padStart(2, '0')}`,
        position: ieee33CustomerTransformerPosition(load.nodeId),
        params: {
          enabled: true,
          transformer_role: 'distribution',
          is_distribution_transformer: true,
          rated_kva: transformerKva,
          primary_voltage_kv: 10,
          voltage_level_kv: 0.4,
          primary_bus_name: `n${load.nodeId}`,
          dss_bus_name: `n${load.nodeId}_lv`,
          secondary_bus_name: `n${load.nodeId}_lv`,
          primary_conn: 'delta',
          secondary_conn: 'wye',
          xhl_percent: 6,
          percent_r: 1,
          tap: 1,
          phases: 3,
        },
        runtime_binding: null,
        tags: ['ieee33-template'],
      };
    }),
    ...IEEE33_LOADS.map<TopologyNode>((load) => {
      const qRatio = load.kw > 0 ? load.kvar / load.kw : 0.25;
      const transformerKva = standardCustomerTransformerKva(load.kw);
      return {
        id: ieee33LoadNodeId(load.nodeId),
        type: 'load',
        name: `LD${String(load.nodeId).padStart(2, '0')}`,
        position: ieee33LoadPosition(load.nodeId),
        params: {
          enabled: true,
          node_id: load.nodeId,
          dss_bus_name: `n${load.nodeId}_load`,
          dss_load_name: `LD${String(load.nodeId).padStart(2, '0')}`,
          target_kv_ln: 0.4,
          phases: 3,
          category: ieee33LoadCategory(load.nodeId),
          remarks: load.nodeId === 9 ? '配电网模板默认示例配储目标，可按需切换。' : '',
          model_year: 2025,
          design_kw: load.kw,
          kvar: load.kvar,
          q_to_p_ratio: Number(qRatio.toFixed(4)),
          pf: 0.95,
          optimize_storage: load.nodeId === 9,
          allow_grid_export: false,
          transformer_capacity_kva: transformerKva,
          transformer_pf_limit: 0.95,
          transformer_reserve_ratio: 0.15,
          dispatch_mode: 'hybrid',
          run_mode: 'single_user',
        },
        runtime_binding: null,
        tags: ['ieee33-template'],
      };
    }),
  ];

  const edges: TopologyEdge[] = [
    {
      id: 'line_source_tx',
      type: 'normal_line',
      name: '电源-主变连接',
      from_node_id: 'source_grid',
      to_node_id: 'tx_main',
      params: lineParams('LC_CABLE', 0.001),
    },
    ...IEEE33_LINES.map<TopologyEdge>((line) => {
      return {
        id: `line_${line.id}`,
        type: line.id === 'F05_0_09' ? 'special_line' : 'normal_line',
        name: line.id,
        from_node_id: ieee33BusNodeId(line.from),
        to_node_id: ieee33BusNodeId(line.to),
        params: lineParams(line.linecode, line.lengthKm, line.normamps, line.emergamps),
      };
    }),
    ...IEEE33_LOADS.flatMap<TopologyEdge>((load) => {
      const transformerKva = standardCustomerTransformerKva(load.kw);
      const serviceProfile = buildDistributionServiceEdgeProfile(transformerKva, Math.hypot(load.kw, load.kvar), 0.4);
      const serviceNormamps = Math.round(serviceProfile?.ratedCurrentA ?? lineCodeDefaults(SERVICE_LINE_LINECODE).rated_current_a);
      const serviceEmergamps = Math.round(serviceProfile?.emergCurrentA ?? lineCodeDefaults(SERVICE_LINE_LINECODE).emerg_current_a);
      const code = String(load.nodeId).padStart(2, '0');
      return [
        {
          id: `edge_n${load.nodeId}_tx_${code}`,
          type: 'normal_line',
          name: `LD${code}配变高压接入`,
          from_node_id: ieee33BusNodeId(`n${load.nodeId}`),
          to_node_id: ieee33CustomerTransformerNodeId(load.nodeId),
          params: lineParams('LC_CABLE', 0.001),
        },
        {
          id: `edge_tx_load_${code}`,
          type: 'special_line',
          name: `LD${code}低压接户线`,
          from_node_id: ieee33CustomerTransformerNodeId(load.nodeId),
          to_node_id: ieee33LoadNodeId(load.nodeId),
          params: lineParams(SERVICE_LINE_LINECODE, SERVICE_LINE_DEFAULT_LENGTH_KM, serviceNormamps, serviceEmergamps),
        },
      ];
    }),
  ];

  return { nodes: resolveNodeOverlaps(nodes), edges, economic_parameters: { ...ECONOMIC_DEFAULT_PARAMS } };
}

export default function TopologyPage() {
  const { projectId = '' } = useParams();

  const [savingEconomic, setSavingEconomic] = useState(false);
  const [savingTopology, setSavingTopology] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [templateConfirmOpen, setTemplateConfirmOpen] = useState(false);
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [saveTemplateName, setSaveTemplateName] = useState('');
  const [saveTemplateDesc, setSaveTemplateDesc] = useState('');
  const [saveTemplateSaving, setSaveTemplateSaving] = useState(false);
  const [lastSavedEconomicSnapshot, setLastSavedEconomicSnapshot] = useState('');
  const [lastSavedEconomicAt, setLastSavedEconomicAt] = useState<Date | null>(null);
  const [lastSavedTopologySnapshot, setLastSavedTopologySnapshot] = useState('');
  const [lastSavedTopologyAt, setLastSavedTopologyAt] = useState<Date | null>(null);
  const [modelPreviewExpanded, setModelPreviewExpanded] = useState(false);

  const [topology, setTopology] = useState<TopologyData>({
    nodes: [],
    edges: [],
    economic_parameters: { ...ECONOMIC_DEFAULT_PARAMS },
  });
  const [inferenceRowsByNodeId, setInferenceRowsByNodeId] = useState<Record<string, SearchSpaceInferenceRow>>({});
  const [editorText, setEditorText] = useState<string>(EMPTY_TOPOLOGY_TEXT);
  const [selection, setSelection] = useState<Selection>(null);
  const [nodeParamsDraft, setNodeParamsDraft] = useState('{}');
  const [edgeParamsDraft, setEdgeParamsDraft] = useState('{}');

  const [connectionMode, setConnectionMode] = useState(false);
  const [pendingLineStart, setPendingLineStart] = useState<string | null>(null);
  const [propertyModalOpen, setPropertyModalOpen] = useState(false);
  const [canvasFullscreen, setCanvasFullscreen] = useState(false);
  const [propertyPanelHeight, setPropertyPanelHeight] = useState<number | null>(null);

  const [jsonCollapsed, setJsonCollapsed] = useState(true);

  const canvasRef = useRef<HTMLDivElement | null>(null);
  const canvasCardRef = useRef<HTMLElement | null>(null);
  const lineToolsRef = useRef<HTMLElement | null>(null);
  const topologySummaryRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<{
    nodeId: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  async function refreshInferenceRows() {
    if (!projectId) {
      setInferenceRowsByNodeId({});
      return;
    }
    try {
      const response = await fetchSearchSpaceInference(projectId);
      const next: Record<string, SearchSpaceInferenceRow> = {};
      response.rows.forEach((row) => {
        if (row.node_id) next[row.node_id] = row;
      });
      setInferenceRowsByNodeId(next);
    } catch {
      setInferenceRowsByNodeId({});
    }
  }

  async function loadTopology() {
    if (!projectId) return;
    setError(null);
    setMessage(null);
    try {
      const data = await fetchProjectTopology(projectId);
      const normalized = normalizeTopology(data);
      setTopology(normalized);
      setEditorText(stringifyTopology(normalized));
      setLastSavedEconomicSnapshot(stringifyEconomicParams(normalized.economic_parameters));
      setLastSavedTopologySnapshot(JSON.stringify({ nodes: normalized.nodes, edges: normalized.edges }));
      setLastSavedEconomicAt(null);
      setLastSavedTopologyAt(null);
      if (!selection && normalized.nodes.length > 0) {
        setSelection({ kind: 'node', id: normalized.nodes[0].id });
      }
      void refreshInferenceRows();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setTopology({ nodes: [], edges: [], economic_parameters: { ...ECONOMIC_DEFAULT_PARAMS } });
      setEditorText(EMPTY_TOPOLOGY_TEXT);
      setInferenceRowsByNodeId({});
    }
  }

  useEffect(() => {
    void loadTopology();
    void refreshTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, TopologyNode>();
    topology.nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [topology]);

  const selectedNode =
    selection?.kind === 'node' ? topology.nodes.find((n) => n.id === selection.id) ?? null : null;
  const selectedLoadInference =
    selectedNode?.type === 'load' ? inferenceRowsByNodeId[selectedNode.id] : undefined;
  const selectedLoadInferenceBasis = selectedLoadInference?.basis?.filter(Boolean) ?? [];
  const selectedLoadInferenceNotes = selectedLoadInference?.notes?.filter(Boolean) ?? [];
  const selectedLoadInferenceExplain = selectedLoadInference?.explain?.filter(Boolean) ?? [];

  const selectedEdge =
    selection?.kind === 'edge' ? topology.edges.find((e) => e.id === selection.id) ?? null : null;
  const selectedEdgeMeta = useMemo(
    () => (selectedEdge ? edgeVisualMeta(selectedEdge, nodeMap) : null),
    [selectedEdge, nodeMap],
  );
  const selectedNodeParamsText = useMemo(
    () => JSON.stringify(editableNodeParams(selectedNode), null, 2),
    [selectedNode],
  );
  const selectedEdgeParamsText = useMemo(
    () => JSON.stringify(editableEdgeParams(selectedEdge), null, 2),
    [selectedEdge],
  );
  const economicParams = topology.economic_parameters;
  const economicSnapshot = useMemo(() => stringifyEconomicParams(economicParams), [economicParams]);
  const economicSaveStatus = useMemo(() => {
    if (savingEconomic) return { saved: false, text: '保存中...' };
    if (!lastSavedEconomicSnapshot) return { saved: false, text: '等待保存' };
    if (lastSavedEconomicSnapshot === economicSnapshot) {
      return {
        saved: true,
        text: lastSavedEconomicAt
          ? `已保存 ${lastSavedEconomicAt.toLocaleTimeString('zh-CN')}`
          : '已从项目读取',
      };
    }
    return { saved: false, text: '有未保存修改' };
  }, [economicSnapshot, lastSavedEconomicAt, lastSavedEconomicSnapshot, savingEconomic]);

  const topologySnapshot = useMemo(
    () => JSON.stringify({ nodes: topology.nodes, edges: topology.edges }),
    [topology.nodes, topology.edges],
  );
  const topologySaveStatus = useMemo(() => {
    if (savingTopology) return { saved: false, text: '保存中...' };
    if (!lastSavedTopologySnapshot) return { saved: false, text: '等待保存' };
    if (lastSavedTopologySnapshot === topologySnapshot) {
      return {
        saved: true,
        text: lastSavedTopologyAt
          ? `已保存 ${lastSavedTopologyAt.toLocaleTimeString('zh-CN')}`
          : '已从项目读取',
      };
    }
    return { saved: false, text: '有未保存修改' };
  }, [topologySnapshot, lastSavedTopologyAt, lastSavedTopologySnapshot, savingTopology]);

  const selectedLoadVoltageMissing =
    selectedNode?.type === 'load' &&
    !hasPositiveNumberParam(selectedNode.params, 'target_kv_ln');
  const selectedLoadDesignMissing =
    selectedNode?.type === 'load' && !hasPositiveNumberParam(selectedNode.params, 'design_kw');
  const selectedLoadStorageEnabled =
    selectedNode?.type === 'load' && booleanParam(selectedNode.params, 'optimize_storage', true);
  const selectedLoadPowerFactor =
    selectedNode?.type === 'load' ? getLoadPowerFactor(selectedNode.params) : null;
  const storageControlledInputStyle = selectedLoadStorageEnabled ? inputStyle : disabledInputStyle;
  const storageControlledLabel: '求解必填' | undefined = selectedLoadStorageEnabled ? '求解必填' : undefined;
  const auxServiceEnabled = booleanParam(economicParams, 'include_aux_service_revenue', false);
  const demandSavingEnabled = booleanParam(economicParams, 'include_demand_saving', true);
  const capacityRevenueEnabled = booleanParam(economicParams, 'include_capacity_revenue', false);
  const lossReductionEnabled = booleanParam(economicParams, 'include_loss_reduction_revenue', false);
  const degradationCostEnabled = booleanParam(economicParams, 'include_degradation_cost', true);
  const replacementCostEnabled = booleanParam(economicParams, 'include_replacement_cost', true);
  const governmentSubsidyEnabled = booleanParam(economicParams, 'include_government_subsidy', false);

  const dssPreview = useMemo(() => buildDssPreview(topology), [topology]);
  const measuredPropertyPanelStyle = useMemo<React.CSSProperties>(() => {
    if (canvasFullscreen || propertyPanelHeight == null) return propertyPanelStyle;
    return {
      ...propertyPanelStyle,
      height: propertyPanelHeight,
      maxHeight: propertyPanelHeight,
    };
  }, [canvasFullscreen, propertyPanelHeight]);

  useEffect(() => {
    const element = canvasRef.current;
    if (!element) return undefined;
    const guardWheel = (event: WheelEvent) => {
      if (canvasFullscreen) event.preventDefault();
    };
    element.addEventListener('wheel', guardWheel, { passive: false });
    return () => element.removeEventListener('wheel', guardWheel);
  }, [canvasFullscreen]);

  useEffect(() => {
    if (canvasFullscreen) {
      setPropertyPanelHeight(null);
      return;
    }

    function updatePropertyPanelHeight() {
      const canvasCard = canvasCardRef.current;
      const lineTools = lineToolsRef.current;
      const topologySummary = topologySummaryRef.current;
      if (!canvasCard || !lineTools || !topologySummary) return;

      const nextHeight = Math.max(
        260,
        Math.floor(
          canvasCard.getBoundingClientRect().height -
            lineTools.getBoundingClientRect().height -
            topologySummary.getBoundingClientRect().height -
            32,
        )
      );
      setPropertyPanelHeight((current) => (current === nextHeight ? current : nextHeight));
    }

    updatePropertyPanelHeight();
    window.addEventListener('resize', updatePropertyPanelHeight);

    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(updatePropertyPanelHeight) : null;
    if (resizeObserver) {
      if (canvasCardRef.current) resizeObserver.observe(canvasCardRef.current);
      if (lineToolsRef.current) resizeObserver.observe(lineToolsRef.current);
      if (topologySummaryRef.current) resizeObserver.observe(topologySummaryRef.current);
    }

    return () => {
      window.removeEventListener('resize', updatePropertyPanelHeight);
      resizeObserver?.disconnect();
    };
  }, [canvasFullscreen]);

  useEffect(() => {
    setNodeParamsDraft(selectedNodeParamsText);
  }, [selectedNodeParamsText]);

  useEffect(() => {
    setEdgeParamsDraft(selectedEdgeParamsText);
  }, [selectedEdgeParamsText]);

  function updateTopology(next: TopologyDraft) {
    const merged = {
      ...next,
      economic_parameters: normalizeEconomicParams(next.economic_parameters, topology.economic_parameters),
    };
    setTopology(merged);
    setEditorText(stringifyTopology(merged));
  }

  function applyEconomicParam(key: string, value: unknown) {
    const nextParams = {
      ...normalizeEconomicParams(topology.economic_parameters),
      [key]: value,
    };
    if (key === 'demand_charge_yuan_per_kw_month' || key === 'daily_demand_shadow_yuan_per_kw') {
      nextParams.demand_charge_yuan_per_kw_month = value;
      nextParams.daily_demand_shadow_yuan_per_kw = value;
    }
    updateTopology({
      ...topology,
      economic_parameters: nextParams,
    });
  }

  function addNode(type: NodeKind, paramsOverride: Record<string, unknown> = {}) {
    const index = topology.nodes.length + 1;
    const params: Record<string, unknown> = { ...buildNodeDefaultParams(type), ...paramsOverride };
    if (type === 'distribution_transformer') {
      params.transformer_role = 'distribution';
      params.is_distribution_transformer = true;
    }
    const savedType = type === 'distribution_transformer' ? 'transformer' : type;
    const loadCategoryLabel = type === 'load' ? getLoadCategoryVisual(params.category).label : '';
    const codeByType: Record<NodeKind, string> = {
      grid: 'grid',
      transformer: 'tx',
      distribution_transformer: 'user_tx',
      bus: 'bus',
      ring_main_unit: 'rmu',
      branch: 'branch',
      switch: 'sw',
      breaker: 'brk',
      fuse: 'fuse',
      regulator: 'reg',
      capacitor: 'cap',
      pv: 'pv',
      wind: 'wind',
      storage: 'es',
      load: 'load',
    };
    const id =
      `${codeByType[type]}_${String(index).padStart(3, '0')}`;

    const name =
      type === 'grid'
        ? `电网${index}`
        : type === 'transformer'
        ? `主变${index}`
        : type === 'distribution_transformer'
        ? `用户配变${index}`
        : type === 'load'
          ? `${loadCategoryLabel}负荷${index}`
          : type === 'bus'
            ? `母线${index}`
            : type === 'ring_main_unit'
              ? `环网柜${index}`
              : type === 'branch'
                ? `分支点${index}`
                : `${type === 'switch' && booleanParam(params, 'normally_open', false) ? '联络开关' : getNodeLabel(type)}${index}`;
    const nodeSize = getNodeSize(type);
    const canvasEl = canvasRef.current;
    const cascadeOffset = (topology.nodes.length % 6) * 18;
    const baseX = canvasEl
      ? canvasEl.scrollLeft + 80 + cascadeOffset
      : 120 + topology.nodes.length * 70;
    const baseY = canvasEl
      ? canvasEl.scrollTop + 90 + cascadeOffset
      : 120 + topology.nodes.length * 50;

    const nextNode: TopologyNode = {
      id,
      type: savedType,
      name,
      position: {
        x: clamp(baseX, 40, CANVAS_WIDTH - nodeSize.width - 40),
        y: clamp(baseY, 40, CANVAS_HEIGHT - nodeSize.height - 40),
      },
      params,
      runtime_binding: null,
      tags: [],
    };

    const next = {
      nodes: resolveNodeOverlaps([...topology.nodes, nextNode], nextNode.id),
      edges: topology.edges,
    };
    setConnectionMode(false);
    setPendingLineStart(null);
    updateTopology(next);
    setSelection({ kind: 'node', id });
    setPropertyModalOpen(true);
  }

  function _selectParallelCable(requiredAmpA: number) {
  // Returns { name, rac, normamps, parallel }
  const candidates = WIRE_DATA_CU.map((cable) => {
    const n = Math.min(12, Math.max(1, Math.ceil(requiredAmpA / cable.normamps)));
    return { name: cable.name, rac: cable.rac, normamps: cable.normamps * n, parallel: n };
  });
  // Pick lowest total ampacity that meets requirement
  const best = candidates.sort((a, b) => a.normamps - b.normamps).find((c) => c.normamps >= requiredAmpA);
  return best ?? { name: '1000_CU', rac: 0.042875, normamps: 1300, parallel: 1 };
}

function getNormalEdgeCurrent(
  fromNode: TopologyNode | undefined,
  toNode: TopologyNode | undefined,
): number {
  // Find any transformer connected to this edge (distribution or upstream)
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

function selectLineCodeByCurrent(currentA: number): { linecode: string; rated_current_a: number; emerg_current_a: number } {
  if (currentA <= 0) return { linecode: 'LC_LIGHT', rated_current_a: 300, emerg_current_a: 450 };
  const option = LINE_CODE_OPTIONS.find(opt => opt.rated_current_a >= currentA);
  return option
    ? { linecode: option.value, rated_current_a: option.rated_current_a, emerg_current_a: option.emerg_current_a }
    : { linecode: 'LC_CABLE', rated_current_a: 1400, emerg_current_a: 1700 };
}

function inferAutoEdgeParams(
  fromNode: TopologyNode | undefined,
  toNode: TopologyNode | undefined,
): { params: Record<string, unknown>; edgeType: 'normal_line' | 'special_line' } {
  // Determine if this is a distribution transformer → low-side resource (load/pv/storage) edge
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
      // High-current 0.4 kV service: use parallel-cable explicit impedance
      const cable = _selectParallelCable(ratedCurrentA);
      const r1 = cable.rac / cable.parallel;
      const x1 = r1 * WIRE_XR_RATIO;
      return {
        params: {
          length_km: SERVICE_LINE_DEFAULT_LENGTH_KM,
          linecode: '',  // empty → use explicit r1/x1
          r_ohm_per_km: r1,
          x_ohm_per_km: x1,
          r0_ohm_per_km: r1,
          x0_ohm_per_km: x1,
          c1_nf_per_km: 0,
          c0_nf_per_km: 0,
          rated_current_a: ratedCurrentA,
          emerg_current_a: emergCurrentA,
          enabled: true,
          normally_open: false,
          phases: 3,
        },
        edgeType: 'special_line',
      };
    }

    // Below threshold: use standard LC_CABLE linecode
    return {
      params: {
        length_km: SERVICE_LINE_DEFAULT_LENGTH_KM,
        linecode: SERVICE_LINE_LINECODE,
        r_ohm_per_km: lineCodeDefaults(SERVICE_LINE_LINECODE).r_ohm_per_km,
        x_ohm_per_km: lineCodeDefaults(SERVICE_LINE_LINECODE).x_ohm_per_km,
        rated_current_a: ratedCurrentA,
        emerg_current_a: emergCurrentA,
        enabled: true,
        normally_open: false,
        phases: 3,
      },
      edgeType: 'special_line',
    };
  }

  // Default: main / branch line — auto-select linecode by current
  const edgeCurrentA = getNormalEdgeCurrent(fromNode, toNode);
  const { linecode: autoLinecode, rated_current_a, emerg_current_a } = selectLineCodeByCurrent(edgeCurrentA);
  const selected = lineCodeDefaults(autoLinecode);
  return {
    params: {
      length_km: 0.5,
      linecode: autoLinecode,
      r_ohm_per_km: selected.r_ohm_per_km,
      x_ohm_per_km: selected.x_ohm_per_km,
      r0_ohm_per_km: selected.r0_ohm_per_km,
      x0_ohm_per_km: selected.x0_ohm_per_km,
      c1_nf_per_km: selected.c1_nf_per_km,
      c0_nf_per_km: selected.c0_nf_per_km,
      rated_current_a,
      emerg_current_a,
      enabled: true,
      normally_open: false,
      phases: 3,
    },
    edgeType: 'normal_line',
  };
}

function createEdge(fromId: string, toId: string) {
    if (!fromId || !toId || fromId === toId) {
      setError('线路创建失败：起点和终点不能为空，且不能相同。');
      return;
    }
    const exists = topology.edges.some(
      (e) =>
        (e.from_node_id === fromId && e.to_node_id === toId) ||
        (e.from_node_id === toId && e.to_node_id === fromId),
    );
    if (exists) {
      setError('线路已存在。');
      return;
    }

    const nodeMap = new Map(topology.nodes.map((n) => [n.id, n]));
    const fromNode = nodeMap.get(fromId);
    const toNode = nodeMap.get(toId);
    const { params: edgeParams, edgeType } = inferAutoEdgeParams(fromNode, toNode);

    const nextEdge: TopologyEdge = {
      id: `line_${String(topology.edges.length + 1).padStart(3, '0')}`,
      type: edgeType,
      name: `线路${topology.edges.length + 1}`,
      from_node_id: fromId,
      to_node_id: toId,
      params: edgeParams,
    };

    const next = {
      nodes: topology.nodes,
      edges: [...topology.edges, nextEdge],
    };
    updateTopology(next);
    setSelection({ kind: 'edge', id: nextEdge.id });
    setPendingLineStart(null);
    setPropertyModalOpen(true);
    setMessage('线路创建成功。');
    setError(null);
  }

  function handleConnectNode(nodeId: string) {
    if (!connectionMode) return false;
    if (!pendingLineStart) {
      setPendingLineStart(nodeId);
      setSelection({ kind: 'node', id: nodeId });
      setMessage('已选择线路起点，请点击终点。');
      return true;
    }
    if (pendingLineStart === nodeId) {
      setError('线路终点不能与起点相同。');
      return true;
    }
    createEdge(pendingLineStart, nodeId);
    setConnectionMode(false);
    return true;
  }

  function removeSelectedNode() {
    if (!selectedNode) return;
    const nextNodes = topology.nodes.filter((n) => n.id !== selectedNode.id);
    const nextEdges = topology.edges.filter(
      (e) => e.from_node_id !== selectedNode.id && e.to_node_id !== selectedNode.id,
    );
    updateTopology({ nodes: nextNodes, edges: nextEdges });
    setSelection(null);
    setPropertyModalOpen(false);
  }

  function removeSelectedEdge() {
    if (!selectedEdge) return;
    const nextEdges = topology.edges.filter((e) => e.id !== selectedEdge.id);
    updateTopology({ nodes: topology.nodes, edges: nextEdges });
    setSelection(null);
    setPropertyModalOpen(false);
  }

  function applyNodeField(field: keyof TopologyNode, value: unknown) {
    if (!selectedNode) return;
    const updatedNode = { ...selectedNode, [field]: value };
    const nextNodes = topology.nodes.map((node) =>
      node.id === selectedNode.id ? updatedNode : node,
    );
    const nodeMap = new Map(nextNodes.map((n) => [n.id, n]));

    const nextEdges = topology.edges.map((edge) => {
      if (edge.from_node_id !== selectedNode.id && edge.to_node_id !== selectedNode.id) {
        return edge;
      }
      const params = edge.params as Record<string, unknown>;
      const linecode = String(params.linecode ?? '');

      // special_line (接户线): always recalculate
      if (edge.type === 'special_line') {
        const fromNode = nodeMap.get(edge.from_node_id);
        const toNode = nodeMap.get(edge.to_node_id);
        const { params: newParams } = inferAutoEdgeParams(fromNode, toNode);
        return { ...edge, params: newParams };
      }

      // normal_line: skip only if user manually set a non-default linecode
      if (linecode !== '' && linecode !== DEFAULT_LINE_CODE) {
        return edge;
      }

      const fromNode = nodeMap.get(edge.from_node_id);
      const toNode = nodeMap.get(edge.to_node_id);
      const { params: newParams } = inferAutoEdgeParams(fromNode, toNode);
      return { ...edge, params: { ...params, ...newParams } };
    });

    updateTopology({ nodes: nextNodes, edges: nextEdges });
  }

  function applyNodeParams(text: string) {
    if (!selectedNode) return false;
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const params = sanitizeNodeParamsForEditor(selectedNode, parsed);
      applyNodeField('params', params);
      setError(null);
      setMessage('节点高级参数已更新。');
      return true;
    } catch {
      setError('节点高级参数格式错误。');
      return false;
    }
  }

  function applyNodeParam(key: string, value: unknown) {
    if (!selectedNode) return;
    const params = { ...(selectedNode.params ?? {}), [key]: value };
    applyNodeField('params', selectedNode.type === 'load' ? cleanLoadPanelParams(params) : params);
  }

  function applyEdgeField(field: keyof TopologyEdge, value: unknown) {
    if (!selectedEdge) return;
    const nextEdges = topology.edges.map((edge) =>
      edge.id === selectedEdge.id ? { ...edge, [field]: value } : edge,
    );
    updateTopology({ nodes: topology.nodes, edges: nextEdges });
  }

  function applyEdgeParams(text: string) {
    if (!selectedEdge) return false;
    try {
      const params = pickParamKeys(JSON.parse(text) as Record<string, unknown>, EDGE_ADVANCED_PARAM_KEYS);
      applyEdgeField('params', params);
      setError(null);
      setMessage('线路高级参数已更新。');
      return true;
    } catch {
      setError('线路高级参数格式错误。');
      return false;
    }
  }

  function applyEdgeParam(key: string, value: unknown) {
    if (!selectedEdge) return;
    applyEdgeField('params', { ...(selectedEdge.params ?? {}), [key]: value });
  }

  function applyEdgeLineCode(linecode: string) {
    if (!selectedEdge) return;
    const defaults = lineCodeDefaults(linecode);
    applyEdgeField('params', {
      ...(selectedEdge.params ?? {}),
      linecode,
      r_ohm_per_km: defaults.r_ohm_per_km,
      x_ohm_per_km: defaults.x_ohm_per_km,
      r0_ohm_per_km: defaults.r0_ohm_per_km,
      x0_ohm_per_km: defaults.x0_ohm_per_km,
      c1_nf_per_km: defaults.c1_nf_per_km,
      c0_nf_per_km: defaults.c0_nf_per_km,
      rated_current_a: defaults.rated_current_a,
      emerg_current_a: defaults.emerg_current_a,
    });
  }

  async function refreshTemplates() {
    try {
      const list = await fetchTemplates();
      setTemplates(list);
    } catch { /* ignore */ }
  }

  async function handleLoadTemplateById(templateId: string) {
    if (!templateId) return;
    setError(null);
    setMessage(null);
    try {
      const templateTopo = await fetchTemplateDetail(templateId);
      if (topology.nodes.length || topology.edges.length) {
        setSelectedTemplateId(templateId);
        setTemplateConfirmOpen(true);
        return;
      }
      updateTopology(templateTopo as unknown as TopologyDraft);
      setMessage('已载入模板配电网模型。请保存拓扑后继续进行构建校验。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleConfirmLoadTemplate() {
    setTemplateConfirmOpen(false);
    const templateId = selectedTemplateId;
    setSelectedTemplateId('');
    if (!templateId) {
      const next = buildIeee33Template();
      updateTopology(next);
      setSelection({ kind: 'node', id: 'tx_main' });
      setError(null);
      setMessage('已载入配电网模板工程：上级电网、主变、10kV馈线、用户配变和低压负荷已放入画布。请保存拓扑后继续进行构建校验。');
      return;
    }
    try {
      const templateTopo = await fetchTemplateDetail(templateId);
      updateTopology(templateTopo as unknown as TopologyDraft);
      setMessage('已载入模板配电网模型。请保存拓扑后继续进行构建校验。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleSaveAsTemplate() {
    if (!saveTemplateName.trim()) return;
    setSaveTemplateSaving(true);
    setError(null);
    try {
      const parsed = normalizeTopology(JSON.parse(editorText));
      await saveTemplate(saveTemplateName.trim(), saveTemplateDesc.trim(), parsed);
      setSaveTemplateOpen(false);
      setSaveTemplateName('');
      setSaveTemplateDesc('');
      setMessage('已保存为配电网模板。');
      await refreshTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaveTemplateSaving(false);
    }
  }

  async function onSaveEconomic() {
    if (!projectId) return;
    setSavingEconomic(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveProjectTopology(projectId, topology);
      const normalized = normalizeTopology(saved);
      const savedEconomicSnapshot = stringifyEconomicParams(normalized.economic_parameters);
      setTopology(normalized);
      setEditorText(stringifyTopology(normalized));
      setLastSavedEconomicSnapshot(savedEconomicSnapshot);
      setLastSavedEconomicAt(new Date());
      setLastSavedTopologySnapshot(JSON.stringify({ nodes: normalized.nodes, edges: normalized.edges }));
      if (!lastSavedTopologyAt) setLastSavedTopologyAt(new Date());
      void refreshInferenceRows();
      setMessage('全局经济参数已保存成功。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingEconomic(false);
    }
  }

  async function onSaveTopology() {
    if (!projectId) return;
    setSavingTopology(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveProjectTopology(projectId, topology);
      const normalized = normalizeTopology(saved);
      const savedEconomicSnapshot = stringifyEconomicParams(normalized.economic_parameters);
      setTopology(normalized);
      setEditorText(stringifyTopology(normalized));
      setLastSavedTopologySnapshot(JSON.stringify({ nodes: normalized.nodes, edges: normalized.edges }));
      setLastSavedTopologyAt(new Date());
      setLastSavedEconomicSnapshot(savedEconomicSnapshot);
      if (!lastSavedEconomicAt) setLastSavedEconomicAt(new Date());
      void refreshInferenceRows();
      setMessage('配电网拓扑已保存成功。');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingTopology(false);
    }
  }

  function applyJsonEditor() {
    try {
      const parsed = normalizeTopology(JSON.parse(editorText));
      setTopology(parsed);
      setMessage('JSON 已应用。');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'JSON 解析失败。');
    }
  }

  function autoArrangeCanvas() {
    updateTopology({
      ...topology,
      nodes: resolveNodeOverlaps(topology.nodes),
    });
    setSelection(null);
    setMessage('已自动整理画布元件，重叠卡片已按最小距离推开。');
  }

  function getCanvasPoint(clientX: number, clientY: number) {
    const el = canvasRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      x: clamp(clientX - rect.left + el.scrollLeft, 0, CANVAS_WIDTH),
      y: clamp(clientY - rect.top + el.scrollTop, 0, CANVAS_HEIGHT),
    };
  }

  function handleCanvasWheel(event: React.WheelEvent<HTMLDivElement>) {
    if (!canvasFullscreen) return;
    event.preventDefault();
    event.stopPropagation();
    const el = canvasRef.current;
    if (!el) return;
    el.scrollLeft += event.deltaX;
    el.scrollTop += event.deltaY;
  }

  function onNodeMouseDown(nodeId: string, event: React.MouseEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (handleConnectNode(nodeId)) return;
    const node = nodeMap.get(nodeId);
    const point = getCanvasPoint(event.clientX, event.clientY);
    if (!node?.position || !point) return;

    dragRef.current = {
      nodeId,
      offsetX: point.x - node.position.x,
      offsetY: point.y - node.position.y,
    };
    setSelection({ kind: 'node', id: nodeId });
  }

  useEffect(() => {
    function handleMove(event: MouseEvent) {
      if (!dragRef.current) return;
      const point = getCanvasPoint(event.clientX, event.clientY);
      if (!point) return;

      const { nodeId, offsetX, offsetY } = dragRef.current;

      setTopology((prev) => {
        const nextNodes = prev.nodes.map((node) => {
          if (node.id !== nodeId) return node;
          const size = getNodeSizeForNode(node);
          const nextX = clamp(point.x - offsetX, 0, CANVAS_WIDTH - size.width);
          const nextY = clamp(point.y - offsetY, 0, CANVAS_HEIGHT - size.height);
          return {
            ...node,
            position: { x: nextX, y: nextY },
          };
        });
        const merged = { ...prev, nodes: nextNodes, edges: prev.edges };
        setEditorText(stringifyTopology(merged));
        return merged;
      });
    }

    function handleUp() {
      const lockedNodeId = dragRef.current?.nodeId;
      dragRef.current = null;
      if (!lockedNodeId) return;

      setTopology((prev) => {
        const nextNodes = resolveNodeOverlaps(prev.nodes, lockedNodeId);
        const merged = { ...prev, nodes: nextNodes, edges: prev.edges };
        setEditorText(stringifyTopology(merged));
        return merged;
      });
    }

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, []);

  function renderPaletteControls() {
    return (
      <>
        <div style={paletteGroupTitleStyle}>电源与变压</div>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('grid')}>
          电网/电源
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('transformer')}>
          ⚡ 主变
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('distribution_transformer')}>
          用户配变
        </button>
        <div style={paletteGroupTitleStyle}>网络节点与开关</div>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('bus')}>
          ▉ 母线
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('ring_main_unit')}>
          ▣ 环网柜
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('branch')}>
          ◉ 分支点
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('switch')}>
          开关
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('switch', { normally_open: true })}>
          联络开关
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('breaker')}>
          断路器
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('fuse')}>
          熔断器
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('regulator')}>
          电压调节
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('capacitor')}>
          电容器
        </button>
        <div style={paletteGroupTitleStyle}>负荷与分布式资源</div>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('load', { category: 'industrial' })}>
          工业负荷
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('load', { category: 'commercial' })}>
          商业负荷
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('load', { category: 'residential' })}>
          居民负荷
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('pv')}>
          光伏
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('wind')}>
          风机
        </button>
        <button type="button" style={paletteBtnStyle} onClick={() => addNode('storage')}>
          储能
        </button>
        <div style={paletteGroupTitleStyle}>线路图例</div>
        <div
          style={{
            display: 'grid',
            gap: 8,
            padding: '10px 10px 12px',
            borderRadius: 12,
            border: '1px solid #dbe3ef',
            background: '#f8fbff',
          }}
        >
          {LINE_LEGEND_ITEMS.map((item) => (
            <div
              key={item.label}
              style={{ display: 'grid', gridTemplateColumns: '44px minmax(0, 1fr)', gap: 8, alignItems: 'center' }}
            >
              <svg width="44" height="10" viewBox="0 0 44 10" aria-hidden="true">
                <line
                  x1="2"
                  y1="5"
                  x2="42"
                  y2="5"
                  stroke={item.stroke}
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeDasharray={item.dash}
                />
              </svg>
              <span style={{ fontSize: 12, color: '#475569', lineHeight: 1.35 }}>{item.label}</span>
            </div>
          ))}
        </div>
      </>
    );
  }

  return (
    <div style={{ padding: 20, background: '#f8fafc', minHeight: '100vh' }}>
      <div style={{ maxWidth: 1820, margin: '0 auto' }}>
        {/* Step 1: Template Selection */}
        <section style={{ ...cardStyle, marginBottom: 12, padding: '12px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>1</span>
            <span style={{ fontWeight: 700, fontSize: 14 }}>选择模板</span>
            <select
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              style={{
                padding: '8px 10px', borderRadius: 10, border: '1px solid #d1d5db',
                fontSize: 12, cursor: 'pointer', background: '#fff', minWidth: 160,
              }}
            >
              <option value="">内置 IEEE 33</option>
              {templates.map((t) => (
                <option key={t.template_id} value={t.template_id}>
                  {t.name} ({t.node_count}节点)
                </option>
              ))}
            </select>
            <button
              type="button"
              style={secondaryBtnStyle}
              onClick={() => {
                if (topology.nodes.length || topology.edges.length) {
                  setSelectedTemplateId(selectedTemplateId || '');
                  setTemplateConfirmOpen(true);
                } else if (selectedTemplateId) {
                  handleLoadTemplateById(selectedTemplateId);
                } else {
                  const next = buildIeee33Template();
                  updateTopology(next);
                  setSelection({ kind: 'node', id: 'tx_main' });
                  setError(null);
                  setMessage('已载入配电网模板工程：上级电网、主变、10kV馈线、用户配变和低压负荷已放入画布。请保存拓扑后继续进行构建校验。');
                }
              }}
              title="载入选中的配电网模板"
            >
              载入模板
            </button>
            <Link
              to="/projects"
              style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 600, fontSize: 12, marginLeft: 'auto' }}
            >
              ← 返回项目列表
            </Link>
          </div>
          <div style={{ fontSize: 10, color: '#64748b' }}>
            当前：{topology.nodes.length ? `${topology.nodes.length}节点 · ${topology.edges.length}线路` : '空白画布'} · 项目：{projectId}
          </div>
        </section>

        {error && <ErrorBanner message={error} />}
        {message ? <div style={successStyle}>{message}</div> : null}

        <ConfirmDialog
          open={templateConfirmOpen}
          onOpenChange={setTemplateConfirmOpen}
          title="载入配电网模板工程"
          description="会替换当前画布中的拓扑，尚未保存的修改将被覆盖。是否继续？"
          onConfirm={handleConfirmLoadTemplate}
        />

        {/* Save-as-template dialog */}
        {saveTemplateOpen && (
          <div style={{
            position: 'fixed', inset: 0, zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,0.4)',
          }} onClick={() => setSaveTemplateOpen(false)}>
            <div style={{
              background: '#fff', borderRadius: 16, padding: 24, maxWidth: 440, width: '100%',
              boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
            }} onClick={(e) => e.stopPropagation()}>
              <h3 style={{ margin: '0 0 16px', fontSize: 20, fontWeight: 700 }}>保存为配电网模板</h3>
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 600, color: '#475569' }}>模板名称</label>
                <input
                  type="text"
                  value={saveTemplateName}
                  onChange={(e) => setSaveTemplateName(e.target.value)}
                  placeholder="请输入模板名称"
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box',
                  }}
                  autoFocus
                />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 600, color: '#475569' }}>模板简介</label>
                <textarea
                  value={saveTemplateDesc}
                  onChange={(e) => setSaveTemplateDesc(e.target.value)}
                  placeholder="请输入模板简介（可选）"
                  rows={3}
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box', resize: 'vertical',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" style={secondaryBtnStyle} onClick={() => setSaveTemplateOpen(false)}>
                  取消
                </button>
                <button type="button" style={primaryBtnStyle}
                  disabled={saveTemplateSaving || !saveTemplateName.trim()}
                  onClick={() => void handleSaveAsTemplate()}
                >
                  {saveTemplateSaving ? '保存中...' : '保存模板'}
                </button>
              </div>
            </div>
          </div>
        )}

        <section style={{ ...cardStyle, marginBottom: 12, padding: '12px 18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>2</span>
            <span style={{ fontWeight: 700, fontSize: 14 }}>全局经济参数</span>
            <span style={{ fontSize: 10, color: economicSaveStatus.saved ? '#16a34a' : '#d97706', fontWeight: 600 }}>
              {economicSaveStatus.text}
            </span>
            <button type="button" style={{ ...primaryBtnStyle, marginLeft: 'auto' }} disabled={savingEconomic} onClick={() => void onSaveEconomic()}>
              {savingEconomic ? '保存中...' : '保存经济参数'}
            </button>
          </div>
          <div style={{ color: '#64748b', fontSize: 12, lineHeight: 1.5, marginBottom: 4 }}>
            这些参数按项目统一生效，构建时会写入所有候选配储目标的 registry 行。
          </div>
          <div style={economicGridStyle}>
            <EconomicParamGroup
              title="辅助服务收益"
              enabled={auxServiceEnabled}
              control={<ToggleParam label="启用" params={economicParams} name="include_aux_service_revenue" fallback={false} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="容量价格 元/kW" name="default_capacity_price_yuan_per_kw" fallback={0.05} step="0.01" reference="参考 0-0.2，默认 0.05" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="履约价格 元/kWh" name="default_delivery_price_yuan_per_kwh" fallback={0.1} step="0.01" reference="参考 0-0.5，默认 0.1" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="罚金价格 元/kWh" name="default_penalty_price_yuan_per_kwh" fallback={0.2} step="0.01" reference="参考 0-1，默认 0.2" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="触发系数" name="default_activation_factor" fallback={0.15} step="0.01" min={0} max={1} reference="参考 0.05-0.3，默认 0.15" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="最大占用比例" name="max_service_power_ratio" fallback={0.3} step="0.01" min={0} max={1} reference="参考 0.1-0.5，默认 0.3" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup
              title="需量收益"
              enabled={demandSavingEnabled}
              control={<ToggleParam label="启用" params={economicParams} name="include_demand_saving" fallback={true} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="需量电价 元/kW·月" name="demand_charge_yuan_per_kw_month" fallback={48} step="0.01" min={0} reference="安徽 10kV 最大需量参考 48" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup
              title="容量收益"
              enabled={capacityRevenueEnabled}
              control={<ToggleParam label="启用" params={economicParams} name="include_capacity_revenue" fallback={false} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="价格 元/kW·日" name="capacity_service_price_yuan_per_kw_day" fallback={0} step="0.01" reference="用户侧基准建议 0；政策情景 0.05-0.2" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="计费天数" name="capacity_revenue_eligible_days" fallback={365} step="1" min={0} max={365} reference="参考 0-365，默认 365" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup
              title="降损收益"
              enabled={lossReductionEnabled}
              control={<ToggleParam label="启用" params={economicParams} name="include_loss_reduction_revenue" fallback={false} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="降损电价 元/kWh" name="network_loss_price_yuan_per_kwh" fallback={0.3} step="0.01" min={0} reference="参考按购电电价或网损价值 0.3" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="网损代理比例" name="network_loss_proxy_rate" fallback={0.02} step="0.001" min={0} reference="仅无 OpenDSS 网损时使用，参考 0.01-0.03" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup
              title="退化成本"
              enabled={degradationCostEnabled}
              control={<ToggleParam label="计入" params={economicParams} name="include_degradation_cost" fallback={true} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="退化成本 元/kWh吞吐" name="degradation_cost_yuan_per_kwh_throughput" fallback={0.03} step="0.001" min={0} reference="由电池成本/寿命折算，参考 0.02-0.08" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="电池成本占比" name="battery_capex_share" fallback={0.6} step="0.01" min={0} max={1} reference="参考 0.5-0.7，默认 0.6" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="循环寿命 EFC" name="cycle_life_efc" fallback={8000} step="100" min={1} reference="磷酸铁锂参考 6000-10000" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="年循环上限 次/年" name="annual_cycle_limit" fallback={0} step="1" min={0} reference="0 表示不设硬约束；保守可填循环寿命/项目寿命，8000/20≈400" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="日历寿命 年" name="calendar_life_years" fallback={20} step="1" min={1} reference="参考 15-20，默认 20" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="日历衰减占比" name="calendar_fade_share" fallback={0.15} step="0.01" min={0} max={1} reference="参考 0.1-0.2，默认 0.15" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="最低成本比例" name="min_degradation_cost_ratio" fallback={0} step="0.01" min={0} reference="保守校核可设 0.02-0.05" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup
              title="更换成本"
              enabled={replacementCostEnabled}
              control={<ToggleParam label="计入" params={economicParams} name="include_replacement_cost" fallback={true} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="更换成本比例" name="replacement_cost_ratio" fallback={0.6} step="0.01" min={0} reference="参考 0.5-0.8，默认 0.6" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="更换年份" name="replacement_year_override" fallback={0} step="1" min={0} reference="0 表示按设备策略库/寿命推断" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="触发 SOH" name="replacement_trigger_soh" fallback={0.7} step="0.01" min={0} max={1} reference="容量衰减到该比例时更换，参考 0.7-0.8" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="更换后 SOH" name="replacement_reset_soh" fallback={0.95} step="0.01" min={0} max={1} reference="更换后可用容量比例，默认 0.95" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup
              title="政府补贴"
              enabled={governmentSubsidyEnabled}
              control={<ToggleParam label="启用" params={economicParams} name="include_government_subsidy" fallback={false} onChange={applyEconomicParam} />}
            >
              <EconomicNumberInput label="补贴比例 占初始投资" name="government_subsidy_rate_on_capex" fallback={0} step="0.01" min={0} reference="安徽用户侧基准 0；敏感性 0.03-0.1" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="容量补贴 元/kWh" name="government_subsidy_yuan_per_kwh" fallback={0} step="0.01" min={0} reference="无明确政策时填 0" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="功率补贴 元/kW" name="government_subsidy_yuan_per_kw" fallback={0} step="0.01" min={0} reference="无明确政策时填 0" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="补贴上限 元" name="government_subsidy_cap_yuan" fallback={0} step="1" min={0} reference="0 表示不设上限" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup title="投资与生命周期">
              <EconomicNumberInput label="项目寿命 年" name="project_life_years" fallback={20} step="1" min={1} reference="工商业储能参考 15-20，默认 20" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="折现率" name="discount_rate" fallback={0.06} step="0.01" min={0} max={1} reference="参考 0.05-0.08，默认 0.06" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="年收益增长率" name="annual_revenue_growth_rate" fallback={0} step="0.01" min={0} reference="基准 0" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="功率侧投资 元/kW" name="power_related_capex_yuan_per_kw" fallback={300} step="1" min={0} reference="仅设备库缺功率价时使用，参考 200-500" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="集成建站附加比例" name="integration_markup_ratio" fallback={0.15} step="0.01" min={0} reference="参考 0.1-0.2，默认 0.15" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="安全消防附加比例" name="safety_markup_ratio" fallback={0.02} step="0.01" min={0} reference="参考 0.02-0.08，默认 0.02" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="其他一次性投资 元" name="other_capex_yuan" fallback={0} step="1" min={0} reference="无额外土建/接入时填 0" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>

            <EconomicParamGroup title="运维与约束">
              <EconomicNumberInput label="固定运维 元/kW·年" name="annual_fixed_om_yuan_per_kw_year" fallback={18} step="0.01" min={0} reference="参考 10-30，默认 18" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="可变运维 元/kWh" name="annual_variable_om_yuan_per_kwh" fallback={0.004} step="0.001" min={0} reference="参考 0.002-0.01，默认 0.004" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="年运维增长率" name="annual_om_growth_rate" fallback={0.02} step="0.01" min={0} reference="参考 0.02" params={economicParams} onChange={applyEconomicParam} />
              <EconomicNumberInput label="电压罚金系数 元" name="voltage_penalty_coeff_yuan" fallback={0} step="1" min={0} reference="基准 0，约束惩罚情景再设置" params={economicParams} onChange={applyEconomicParam} />
            </EconomicParamGroup>
          </div>
        </section>

        {/* Step 3: Edit Topology */}
        <section style={{ ...cardStyle, marginBottom: 12, padding: '10px 16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>3</span>
            <span style={{ fontWeight: 700, fontSize: 14 }}>配电网拓扑建模</span>
            <span style={{ fontSize: 10, color: topologySaveStatus.saved ? '#16a34a' : '#d97706', fontWeight: 600 }}>
              {topologySaveStatus.text}
            </span>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
              <button type="button" style={secondaryBtnStyle} onClick={() => {
                setSaveTemplateName('');
                setSaveTemplateDesc('');
                setSaveTemplateOpen(true);
              }}>
                保存为模板
              </button>
              <button type="button" style={primaryBtnStyle} disabled={savingTopology} onClick={() => void onSaveTopology()}>
                {savingTopology ? '保存中...' : '保存拓扑'}
              </button>
            </div>
          </div>
        </section>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: canvasFullscreen ? 'minmax(0, 1fr)' : '180px minmax(0, 1fr) 320px',
            gap: 16,
            alignItems: 'stretch',
          }}
        >
          <div
            style={{
              display: canvasFullscreen ? 'none' : 'grid',
              minHeight: 0,
            }}
          >
            <section
              style={{
                ...cardStyle,
                height: TOPOLOGY_WORKBENCH_HEIGHT,
                display: 'grid',
                gridTemplateRows: 'auto minmax(0, 1fr) auto',
                boxSizing: 'border-box',
                overflow: 'hidden',
              }}
            >
              <h2 style={sectionTitleStyle}>元件库</h2>
              <div style={{ display: 'grid', gap: 8, overflowY: 'auto', paddingRight: 4 }}>
                {renderPaletteControls()}
              </div>
              <div style={{ marginTop: 12, fontSize: 12, color: '#6b7280', lineHeight: 1.5 }}>
                先添加节点，再在右侧“线路创建”里建立起点和终点。
              </div>
            </section>
          </div>

          <section
            ref={canvasCardRef}
            style={{
              ...(canvasFullscreen ? fullscreenCanvasStyle : cardStyle),
              height: canvasFullscreen ? undefined : TOPOLOGY_WORKBENCH_HEIGHT,
              position: canvasFullscreen ? 'fixed' : 'relative',
              display: 'grid',
              gridTemplateRows: 'auto minmax(0, 1fr)',
              overflow: 'hidden',
              boxSizing: 'border-box',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 12,
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <h2 style={{ ...sectionTitleStyle, marginBottom: 0 }}>可视化画布</h2>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, color: '#94a3b8' }}>
                  {connectionMode ? (pendingLineStart ? '连线模式：请选择终点' : '连线模式：请选择起点') : '支持拖拽调整元件位置'}
                </span>
                {connectionMode ? (
                  <button
                    type="button"
                    style={secondaryBtnStyle}
                    onClick={() => {
                      setConnectionMode(false);
                      setPendingLineStart(null);
                    }}
                  >
                    取消连线
                  </button>
                ) : null}
                <button type="button" style={secondaryBtnStyle} onClick={autoArrangeCanvas}>
                  自动整理布局
                </button>
                <button type="button" style={secondaryBtnStyle} onClick={() => setCanvasFullscreen((value) => !value)}>
                  {canvasFullscreen ? '退出全屏' : '全屏编辑'}
                </button>
              </div>
            </div>

            {canvasFullscreen ? (
              <aside style={fullscreenPaletteStyle}>
                <div style={fullscreenPaletteTitleStyle}>元件库</div>
                <div style={fullscreenPaletteBodyStyle}>
                  <div style={fullscreenLineToolStyle}>
                    <button
                      type="button"
                      style={{ ...(connectionMode ? dangerBtnStyle : primaryBtnStyle), width: '100%' }}
                      onClick={() => {
                        if (connectionMode) {
                          setConnectionMode(false);
                          setPendingLineStart(null);
                          return;
                        }
                        setConnectionMode(true);
                        setPendingLineStart(null);
                      }}
                    >
                      {connectionMode ? '退出连线模式' : '开启连线模式'}
                    </button>
                    <div style={{ fontSize: 12, color: pendingLineStart ? '#1d4ed8' : '#64748b', lineHeight: 1.4 }}>
                      {pendingLineStart ? `起点：${nodeMap.get(pendingLineStart)?.name ?? pendingLineStart}` : '尚未选择起点'}
                    </div>
                  </div>
                  {renderPaletteControls()}
                </div>
              </aside>
            ) : null}

            <div
              ref={canvasRef}
              onWheel={handleCanvasWheel}
              style={{
                position: 'relative',
                width: '100%',
                height: canvasFullscreen ? 'calc(100vh - 120px)' : '100%',
                minHeight: 0,
                overflow: 'auto',
                border: '1px solid #dbe3ef',
                borderRadius: 12,
                background: '#f8fbff',
              }}
              onMouseDown={() => setSelection(null)}
            >
              <div
                style={{
                  position: 'relative',
                  width: CANVAS_WIDTH,
                  height: CANVAS_HEIGHT,
                  backgroundImage:
                    'linear-gradient(to right, rgba(148,163,184,0.18) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.18) 1px, transparent 1px), linear-gradient(to right, rgba(37,99,235,0.13) 1px, transparent 1px), linear-gradient(to bottom, rgba(37,99,235,0.13) 1px, transparent 1px)',
                  backgroundSize: '16px 16px, 16px 16px, 80px 80px, 80px 80px',
                  backgroundPosition: '0 0, 0 0, 0 0, 0 0',
                }}
              >
                <svg
                  width={CANVAS_WIDTH}
                  height={CANVAS_HEIGHT}
                  style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
                >
                  {topology.edges.map((edge) => {
                    const from = nodeMap.get(edge.from_node_id);
                    const to = nodeMap.get(edge.to_node_id);
                    if (!from?.position || !to?.position) return null;
                    const edgeMeta = edgeVisualMeta(edge, nodeMap);

                    const fromCenter = getNodeCenter(from);
                    const toCenter = getNodeCenter(to);
                    const fromPoint = getNodeBoundaryPoint(from, toCenter);
                    const toPoint = getNodeBoundaryPoint(to, fromCenter);
                    const x1 = fromPoint.x;
                    const y1 = fromPoint.y;
                    const x2 = toPoint.x;
                    const y2 = toPoint.y;
                    const mx = (x1 + x2) / 2;
                    const my = (y1 + y2) / 2;

                    return (
                      <g key={edge.id}>
                        <line
                          x1={x1}
                          y1={y1}
                          x2={x2}
                          y2={y2}
                          stroke={edgeMeta.stroke}
                          strokeWidth={selection?.kind === 'edge' && selection.id === edge.id ? 3.2 : 2.1}
                          strokeLinecap="round"
                          strokeDasharray={edgeMeta.dash}
                          pointerEvents="stroke"
                          style={{ cursor: 'pointer' }}
                          onClick={(evt) => {
                            evt.stopPropagation();
                            setSelection({ kind: 'edge', id: edge.id });
                          }}
                          onDoubleClick={(evt) => {
                            evt.stopPropagation();
                            setSelection({ kind: 'edge', id: edge.id });
                            if (canvasFullscreen) setPropertyModalOpen(true);
                          }}
                        />
                        <line
                          x1={x1}
                          y1={y1}
                          x2={x2}
                          y2={y2}
                          stroke="transparent"
                          strokeWidth={14}
                          pointerEvents="stroke"
                          style={{ cursor: 'pointer' }}
                          onClick={(evt) => {
                            evt.stopPropagation();
                            setSelection({ kind: 'edge', id: edge.id });
                          }}
                          onDoubleClick={(evt) => {
                            evt.stopPropagation();
                            setSelection({ kind: 'edge', id: edge.id });
                            if (canvasFullscreen) setPropertyModalOpen(true);
                          }}
                        />
                        <text
                          x={mx}
                          y={my - (edgeMeta.serviceProfile || edgeMeta.dash ? 12 : 5)}
                          textAnchor="middle"
                          fontSize="9"
                          fill="#64748b"
                        >
                          <tspan x={mx} dy="0">
                            {edge.name ?? edge.id}
                          </tspan>
                          {edgeMeta.serviceProfile ? (
                            <tspan x={mx} dy="11" fill={edgeMeta.stroke}>
                              {`${edgeMeta.shortLabel} | ${formatCurrentDisplay(edgeMeta.serviceProfile.ratedCurrentA)}`}
                            </tspan>
                          ) : edgeMeta.dash ? (
                            <tspan x={mx} dy="11" fill={edgeMeta.stroke}>
                              {edgeMeta.categoryLabel}
                            </tspan>
                          ) : null}
                        </text>
                      </g>
                    );
                  })}
                </svg>

                {topology.nodes.map((node) => {
                  const isSelected = selection?.kind === 'node' && selection.id === node.id;
                  const isLineStart = pendingLineStart === node.id;
                  const x = safeNumber(node.position?.x, 100);
                  const y = safeNumber(node.position?.y, 100);
                  const visual = getNodeVisualForNode(node);
                  const size = getNodeSizeForNode(node);
                  const isCompactNode = ['branch', 'capacitor', 'wind'].includes(node.type);
                  const isStorageCandidate =
                    node.type === 'load' && booleanParam(node.params, 'optimize_storage', true);
                  const loadCategory = node.type === 'load' ? getLoadCategory(node.params?.category) : undefined;
                  const loadCategoryVisual = loadCategory ? LOAD_CATEGORY_VISUALS[loadCategory] : null;
                  const loadNodeCode = node.type === 'load' ? getLoadNodeCode(node) : '';
                  const borderColor = isLineStart ? '#2563eb' : isSelected ? '#ef4444' : visual.border;

                  return (
                    <div
                      key={node.id}
                      onMouseDown={(evt) => onNodeMouseDown(node.id, evt)}
                      onClick={(evt) => {
                        evt.stopPropagation();
                        if (connectionMode) return;
                        setSelection({ kind: 'node', id: node.id });
                      }}
                      onDoubleClick={(evt) => {
                        evt.stopPropagation();
                        setSelection({ kind: 'node', id: node.id });
                        if (canvasFullscreen) setPropertyModalOpen(true);
                      }}
                      style={{
                        position: 'absolute',
                        left: x,
                        top: y,
                        width: size.width,
                        height: size.height,
                        background: visual.background,
                        border: `2px solid ${borderColor}`,
                        borderRadius: visual.radius,
                        clipPath: visual.clipPath,
                        boxShadow: isLineStart
                          ? '0 0 0 5px rgba(37,99,235,0.18), 0 10px 20px rgba(15, 23, 42, 0.10)'
                          : isSelected
                            ? '0 0 0 4px rgba(239,68,68,0.16), 0 10px 20px rgba(15, 23, 42, 0.12)'
                            : '0 7px 18px rgba(15, 23, 42, 0.08)',
                        padding: isCompactNode ? '6px' : '7px 8px',
                        boxSizing: 'border-box',
                        display: 'grid',
                        gridTemplateColumns: isCompactNode ? '1fr' : '30px minmax(0, 1fr)',
                        alignItems: 'center',
                        gap: isCompactNode ? 3 : 7,
                        cursor: connectionMode ? 'crosshair' : 'move',
                        userSelect: 'none',
                        overflow: 'hidden',
                      }}
                    >
                      <NodeGlyph type={node.type} color={visual.color} compact={isCompactNode} category={loadCategory} />
                      <div style={{ minWidth: 0, textAlign: isCompactNode ? 'center' : 'left' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: isCompactNode ? 'center' : 'flex-start', gap: 5, minWidth: 0 }}>
                          <strong style={loadNodeCode ? loadNodeCodeStyle : nodeNameStyle}>
                            {loadNodeCode || node.name || node.id}
                          </strong>
                          {node.type === 'load' ? (
                            <span style={isStorageCandidate ? candidateBadgeStyle : backgroundLoadBadgeStyle}>
                              {isStorageCandidate ? '候选' : '背景'}
                            </span>
                          ) : null}
                        </div>
                        <div style={{ ...nodeTypeTextStyle, color: visual.color }}>
                          {loadCategoryVisual ? `${loadCategoryVisual.label}负荷` : getNodeLabelForNode(node)}
                        </div>
                        {!isCompactNode ? (
                          <div style={nodeDetailTextStyle}>{getNodeDetail(node)}</div>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          <div
            style={{
              display: canvasFullscreen && !propertyModalOpen ? 'none' : 'grid',
              gridTemplateRows: canvasFullscreen ? 'auto minmax(0, 1fr)' : 'auto auto minmax(0, 1fr)',
              alignSelf: 'stretch',
              gap: 16,
              height: canvasFullscreen ? undefined : TOPOLOGY_WORKBENCH_HEIGHT,
              minHeight: 0,
            }}
          >
            <section ref={lineToolsRef} style={cardStyle}>
              <h2 style={sectionTitleStyle}>线路创建</h2>

              <div style={{ marginTop: 2 }}>
                <button
                  type="button"
                  style={connectionMode ? dangerBtnStyle : primaryBtnStyle}
                  onClick={() => {
                    setConnectionMode((value) => !value);
                    setPendingLineStart(null);
                  }}
                >
                  {connectionMode ? '退出连线模式' : '开启连线模式'}
                </button>
              </div>
              <div style={{ marginTop: 10, fontSize: 12, color: pendingLineStart ? '#1d4ed8' : '#64748b' }}>
                {pendingLineStart ? `起点：${nodeMap.get(pendingLineStart)?.name ?? pendingLineStart}` : '尚未选择起点'}
              </div>
            </section>

            {!canvasFullscreen ? (
              <section ref={topologySummaryRef} style={cardStyle}>
                <h2 style={sectionTitleStyle}>拓扑摘要</h2>
                <SummaryRow label="节点数" value={String(topology.nodes.length)} />
                <SummaryRow label="线路数" value={String(topology.edges.length)} />
                <div style={{ marginTop: 12, fontSize: 12, color: '#6b7280', lineHeight: 1.5 }}>
                  摘要随拓扑保存同步更新，当前列与画布保持同高。
                </div>
              </section>
            ) : null}

            {propertyModalOpen && (selectedNode || selectedEdge) ? (
              <div style={modalBackdropStyle} onMouseDown={() => setPropertyModalOpen(false)} />
            ) : null}

            <section style={propertyModalOpen && (selectedNode || selectedEdge) ? propertyModalStyle : measuredPropertyPanelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexShrink: 0 }}>
                <h2 style={sectionTitleStyle}>属性面板</h2>
                <div style={{ display: 'flex', gap: 8 }}>
                  {propertyModalOpen ? (
                    <button type="button" style={secondaryBtnStyle} onClick={() => setPropertyModalOpen(false)}>
                      关闭
                    </button>
                  ) : null}
                </div>
              </div>
              <div style={requiredLegendStyle}>
                <span style={requiredBadgeStyle}>必填</span>
                <span>构建校验依赖</span>
                <span style={recommendedBadgeStyle}>建议</span>
                <span>可自动补齐但建议明确填写</span>
                <span style={recommendedBadgeStyle}>求解必填</span>
                <span>影响优化计算</span>
              </div>

              {selectedNode ? (
                <>
                <div style={propertyPanelBodyStyle}>
                  <div style={propertyPanelHeadingStyle}>节点：{selectedNode.id}</div>
                  <PropertyGroupTitle>基本信息</PropertyGroupTitle>

                  <label style={labelStyle}>名称</label>
                  <input
                    value={selectedNode.name ?? ''}
                    onChange={(e) => applyNodeField('name', e.target.value)}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>类型</label>
                  <input value={getNodeLabelForNode(selectedNode)} readOnly style={inputStyle} />

                  <PropertyGroupTitle>潮流模型</PropertyGroupTitle>

                  <FieldLabel marker="必填">潮流模型相数</FieldLabel>
                  <select value="3" onChange={() => applyNodeParam('phases', 3)} style={inputStyle}>
                    <option value="3">三相平衡</option>
                  </select>

                  {selectedNode.type === 'grid' || selectedNode.type === 'source' ? (
                    <>
                      <FieldLabel marker="建议">电源母线名称</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'source_bus', 'sourcebus')}
                        onChange={(e) => applyNodeParam('source_bus', e.target.value)}
                        style={inputStyle}
                      />
                    </>
                  ) : (
                    <>
                      <FieldLabel marker="建议">潮流模型母线名</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'dss_bus_name', '')}
                        placeholder={selectedNode.type === 'load' ? '例如 n9；为空时按节点编号生成' : '例如 n0、f01_j1'}
                        onChange={(e) => applyNodeParam('dss_bus_name', e.target.value)}
                        style={inputStyle}
                      />
                    </>
                  )}

                  <PropertyGroupTitle>画布位置</PropertyGroupTitle>

                  <label style={labelStyle}>横向位置</label>
                  <input
                    value={String(selectedNode.position?.x ?? 0)}
                    onChange={(e) =>
                      applyNodeField('position', {
                        x: Number(e.target.value || 0),
                        y: selectedNode.position?.y ?? 0,
                      })
                    }
                    style={inputStyle}
                  />

                  <label style={labelStyle}>纵向位置</label>
                  <input
                    value={String(selectedNode.position?.y ?? 0)}
                    onChange={(e) =>
                      applyNodeField('position', {
                        x: selectedNode.position?.x ?? 0,
                        y: Number(e.target.value || 0),
                      })
                    }
                    style={inputStyle}
                  />

                  {selectedNode.type === 'grid' || selectedNode.type === 'source' ? (
                    <>
                      <PropertyGroupTitle>电源参数</PropertyGroupTitle>

                      <FieldLabel marker="建议">基准电压 kV</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'base_kv', 110)}
                        onChange={(e) => applyNodeParam('base_kv', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">标幺电压 pu</FieldLabel>
                      <input
                        type="number"
                        step="0.01"
                        value={numberParam(selectedNode.params, 'pu', 1)}
                        onChange={(e) => applyNodeParam('pu', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">三相短路容量 MVA</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'mvasc3', 1000)}
                        onChange={(e) => applyNodeParam('mvasc3', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">单相短路容量 MVA</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'mvasc1', numberParam(selectedNode.params, 'mvasc3', 1000))}
                        onChange={(e) => applyNodeParam('mvasc1', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">正序 X/R</FieldLabel>
                      <input
                        type="number"
                        step="0.1"
                        value={numberParam(selectedNode.params, 'x1r1', 10)}
                        onChange={(e) => applyNodeParam('x1r1', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">零序 X/R</FieldLabel>
                      <input
                        type="number"
                        step="0.1"
                        value={numberParam(selectedNode.params, 'x0r0', 3)}
                        onChange={(e) => applyNodeParam('x0r0', Number(e.target.value || 0))}
                        style={inputStyle}
                      />
                    </>
                  ) : null}

                  {isTransformerType(selectedNode.type) ? (
                    <>
                      <PropertyGroupTitle>{isDistributionTransformerNode(selectedNode) ? '用户配变参数' : '变压器参数'}</PropertyGroupTitle>

                      <FieldLabel marker="建议">额定容量 kVA</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'rated_kva', isDistributionTransformerNode(selectedNode) ? 1000 : 31500)}
                        onChange={(e) => applyNodeParam('rated_kva', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">低压侧基准电压 kV</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'voltage_level_kv', isDistributionTransformerNode(selectedNode) ? 0.4 : 10)}
                        onChange={(e) => applyNodeParam('voltage_level_kv', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">高压侧基准电压 kV</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'primary_voltage_kv', isDistributionTransformerNode(selectedNode) ? 10 : 110)}
                        onChange={(e) => applyNodeParam('primary_voltage_kv', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">高压侧母线名称</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'primary_bus_name', isDistributionTransformerNode(selectedNode) ? '' : 'sourcebus')}
                        placeholder={isDistributionTransformerNode(selectedNode) ? '可留空，Build 按连接关系推断' : 'sourcebus'}
                        onChange={(e) => applyNodeParam('primary_bus_name', e.target.value)}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">短路电抗 XHL %</FieldLabel>
                      <input
                        type="number"
                        step="0.1"
                        value={numberParam(selectedNode.params, 'xhl_percent', 7)}
                        onChange={(e) => applyNodeParam('xhl_percent', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">绕组电阻 %R</FieldLabel>
                      <input
                        type="number"
                        step="0.01"
                        value={numberParam(selectedNode.params, 'percent_r', 0.5)}
                        onChange={(e) => applyNodeParam('percent_r', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">低压侧固定 tap</FieldLabel>
                      <input
                        type="number"
                        step="0.001"
                        value={numberParam(selectedNode.params, 'tap', 1)}
                        onChange={(e) => applyNodeParam('tap', Number(e.target.value || 0))}
                        style={inputStyle}
                      />
                    </> 
                  ) : null}

                  {isBusEquipmentType(selectedNode.type) ? (
                    <>
                      <PropertyGroupTitle>节点电气参数</PropertyGroupTitle>

                      <FieldLabel marker="建议">基准电压 kV</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'voltage_level_kv', 10)}
                        onChange={(e) => applyNodeParam('voltage_level_kv', Number(e.target.value || 0))}
                        style={inputStyle}
                      />
                    </>
                  ) : null}

                  {selectedNode.type === 'switch' || selectedNode.type === 'breaker' || selectedNode.type === 'fuse' ? (
                    <>
                      <PropertyGroupTitle>开关保护映射</PropertyGroupTitle>

                      <label style={labelStyle}>设备状态</label>
                      <select
                        value={String(booleanParam(selectedNode.params, 'enabled', true))}
                        onChange={(e) => applyNodeParam('enabled', e.target.value === 'true')}
                        style={inputStyle}
                      >
                        <option value="true">投入</option>
                        <option value="false">退出</option>
                      </select>

                      <ToggleParam
                        label="常开/断开"
                        params={selectedNode.params}
                        name="normally_open"
                        fallback={false}
                        onChange={applyNodeParam}
                      />

                      <FieldLabel marker="映射必填">目标线路 ID</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'target_line', '')}
                        placeholder="例如 line_F12_0_26 或 line_003"
                        onChange={(e) => applyNodeParam('target_line', e.target.value)}
                        style={inputStyle}
                      />

                      {selectedNode.type === 'fuse' ? (
                        <>
                          <FieldLabel marker="建议">熔丝额定电流 A</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'rated_current_a', 200)}
                            onChange={(e) => applyNodeParam('rated_current_a', Number(e.target.value || 0))}
                            style={inputStyle}
                          />
                        </>
                      ) : null}
                    </>
                  ) : null}

                  {selectedNode.type === 'regulator' ? (
                    <>
                      <PropertyGroupTitle>电压调节控制</PropertyGroupTitle>

                      <label style={labelStyle}>启用控制</label>
                      <select
                        value={String(booleanParam(selectedNode.params, 'enabled', true))}
                        onChange={(e) => applyNodeParam('enabled', e.target.value === 'true')}
                        style={inputStyle}
                      >
                        <option value="true">启用</option>
                        <option value="false">停用</option>
                      </select>

                      <FieldLabel marker="映射必填">目标变压器名</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'target_transformer', '')}
                        placeholder="例如 tx_main 或 user_tx_001"
                        onChange={(e) => applyNodeParam('target_transformer', e.target.value)}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">控制绕组</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'winding', 2)}
                        onChange={(e) => applyNodeParam('winding', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">目标电压 V</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'vreg', 120)}
                        onChange={(e) => applyNodeParam('vreg', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">死区 V</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'band', 2)}
                        onChange={(e) => applyNodeParam('band', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">PT 变比</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'ptratio', 60)}
                        onChange={(e) => applyNodeParam('ptratio', Number(e.target.value || 0))}
                        style={inputStyle}
                      />
                    </>
                  ) : null}

                  {selectedNode.type === 'capacitor' ? (
                    <>
                      <PropertyGroupTitle>无功补偿参数</PropertyGroupTitle>

                      <label style={labelStyle}>启用电容器</label>
                      <select
                        value={String(booleanParam(selectedNode.params, 'enabled', true))}
                        onChange={(e) => applyNodeParam('enabled', e.target.value === 'true')}
                        style={inputStyle}
                      >
                        <option value="true">启用</option>
                        <option value="false">停用</option>
                      </select>

                      <FieldLabel marker="必填">容量 kvar</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'kvar', 300)}
                        onChange={(e) => applyNodeParam('kvar', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <label style={labelStyle}>接线方式</label>
                      <select
                        value={stringParam(selectedNode.params, 'connection', 'wye')}
                        onChange={(e) => applyNodeParam('connection', e.target.value)}
                        style={inputStyle}
                      >
                        <option value="wye">wye</option>
                        <option value="delta">delta</option>
                      </select>
                    </>
                  ) : null}

                  {isResourceType(selectedNode.type) ? (
                    <>
                      <PropertyGroupTitle>分布式资源参数</PropertyGroupTitle>

                      <label style={labelStyle}>启用元件</label>
                      <select
                        value={String(booleanParam(selectedNode.params, 'enabled', true))}
                        onChange={(e) => applyNodeParam('enabled', e.target.value === 'true')}
                        style={inputStyle}
                      >
                        <option value="true">启用</option>
                        <option value="false">停用</option>
                      </select>

                      <FieldLabel marker="建议">潮流模型元件名</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'dss_name', '')}
                        placeholder="为空时按节点 ID 生成"
                        onChange={(e) => applyNodeParam('dss_name', e.target.value)}
                        style={inputStyle}
                      />

                      <FieldLabel marker="必填">接入基准电压 kV</FieldLabel>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'voltage_level_kv', 0.4)}
                        onChange={(e) => applyNodeParam('voltage_level_kv', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      {selectedNode.type === 'pv' ? (
                        <>
                          <FieldLabel marker="必填">光伏容量 Pmpp kW</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'pmpp_kw', 100)}
                            onChange={(e) => applyNodeParam('pmpp_kw', Number(e.target.value || 0))}
                            style={inputStyle}
                          />

                          <FieldLabel marker="建议">逆变器容量 kVA</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'kva', numberParam(selectedNode.params, 'pmpp_kw', 100))}
                            onChange={(e) => applyNodeParam('kva', Number(e.target.value || 0))}
                            style={inputStyle}
                          />

                          <FieldLabel marker="建议">辐照度系数</FieldLabel>
                          <input
                            type="number"
                            step="0.01"
                            value={numberParam(selectedNode.params, 'irradiance', 1)}
                            onChange={(e) => applyNodeParam('irradiance', Number(e.target.value || 0))}
                            style={inputStyle}
                          />
                        </>
                      ) : null}

                      {selectedNode.type === 'wind' ? (
                        <>
                          <FieldLabel marker="必填">风机有功 kW</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'rated_kw', 100)}
                            onChange={(e) => applyNodeParam('rated_kw', Number(e.target.value || 0))}
                            style={inputStyle}
                          />

                          <FieldLabel marker="建议">功率因数</FieldLabel>
                          <input
                            type="number"
                            step="0.01"
                            value={numberParam(selectedNode.params, 'pf', 0.98)}
                            onChange={(e) => applyNodeParam('pf', Number(e.target.value || 0))}
                            style={inputStyle}
                          />
                        </>
                      ) : null}

                      {selectedNode.type === 'storage' ? (
                        <>
                          <FieldLabel marker="必填">额定功率 kW</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'rated_kw', 100)}
                            onChange={(e) => applyNodeParam('rated_kw', Number(e.target.value || 0))}
                            style={inputStyle}
                          />

                          <FieldLabel marker="必填">额定容量 kWh</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'rated_kwh', 215)}
                            onChange={(e) => applyNodeParam('rated_kwh', Number(e.target.value || 0))}
                            style={inputStyle}
                          />

                          <FieldLabel marker="建议">初始 SOC %</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'initial_soc_pct', 50)}
                            onChange={(e) => applyNodeParam('initial_soc_pct', Number(e.target.value || 0))}
                            style={inputStyle}
                          />

                          <FieldLabel marker="建议">保留 SOC %</FieldLabel>
                          <input
                            type="number"
                            value={numberParam(selectedNode.params, 'reserve_soc_pct', 10)}
                            onChange={(e) => applyNodeParam('reserve_soc_pct', Number(e.target.value || 0))}
                            style={inputStyle}
                          />
                        </>
                      ) : null}
                    </>
                  ) : null}

                  {selectedNode.type === 'load' ? (
                    <>
                      <PropertyGroupTitle>负荷识别与运行</PropertyGroupTitle>

                      <label style={labelStyle}>启用节点</label>
                      <select
                        value={String(booleanParam(selectedNode.params, 'enabled', true))}
                        onChange={(e) => applyNodeParam('enabled', e.target.value === 'true')}
                        style={inputStyle}
                      >
                        <option value="true">启用</option>
                        <option value="false">停用</option>
                      </select>

                      <FieldLabel marker="建议">节点编号</FieldLabel>
                      <input
                        type="number"
                        value={numberInputValue(selectedNode.params, 'node_id')}
                        placeholder="留空则按负荷顺序补齐"
                        onChange={(e) => applyNodeParam('node_id', e.target.value === '' ? null : Number(e.target.value))}
                        style={inputStyle}
                      />

                      <FieldLabel marker="建议">潮流模型负荷名</FieldLabel>
                      <input
                        value={stringParam(selectedNode.params, 'dss_load_name', '')}
                        placeholder="例如 LD09；为空时按节点编号生成"
                        onChange={(e) => applyNodeParam('dss_load_name', e.target.value)}
                        style={inputStyle}
                      />

                      <FieldLabel marker="必填" missing={selectedLoadVoltageMissing}>基准电压 kV</FieldLabel>
                      <input
                        type="number"
                        step="0.0001"
                        value={numberInputValue(selectedNode.params, 'target_kv_ln')}
                        placeholder="例如 10"
                        onChange={(e) => applyNodeParam('target_kv_ln', e.target.value === '' ? null : Number(e.target.value))}
                        style={selectedLoadVoltageMissing ? missingRequiredInputStyle : inputStyle}
                      />

                      <label style={labelStyle}>负荷类别</label>
                      <select
                        value={stringParam(selectedNode.params, 'category', 'industrial')}
                        onChange={(e) => applyNodeParam('category', e.target.value)}
                        style={inputStyle}
                      >
                        <option value="industrial">工业</option>
                        <option value="commercial">商业</option>
                        <option value="residential">居民</option>
                      </select>

                      <label style={labelStyle}>备注</label>
                      <input
                        value={stringParam(selectedNode.params, 'remarks', '') || stringParam(selectedNode.params, 'description', '')}
                        onChange={(e) => applyNodeParam('remarks', e.target.value)}
                        style={inputStyle}
                      />

                      <label style={labelStyle}>模型年份</label>
                      <input
                        type="number"
                        value={numberParam(selectedNode.params, 'model_year', 2025)}
                        onChange={(e) => applyNodeParam('model_year', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <PropertyGroupTitle>负荷电气参数</PropertyGroupTitle>

                      <FieldLabel marker="求解必填" missing={selectedLoadDesignMissing}>设计负荷 kW</FieldLabel>
                      <input
                        type="number"
                        value={numberInputValue(selectedNode.params, 'design_kw')}
                        placeholder="例如 800"
                        onChange={(e) => applyNodeParam('design_kw', e.target.value === '' ? null : Number(e.target.value))}
                        style={selectedLoadDesignMissing ? missingRequiredInputStyle : inputStyle}
                      />

                      <label style={labelStyle}>无功/有功比</label>
                      <input
                        type="number"
                        step="0.01"
                        value={numberParam(selectedNode.params, 'q_to_p_ratio', 0.25)}
                        onChange={(e) => applyNodeParam('q_to_p_ratio', Number(e.target.value || 0))}
                        style={inputStyle}
                      />

                      <label style={labelStyle}>参考功率因数</label>
                      <input
                        type="text"
                        value={selectedLoadPowerFactor == null ? '' : selectedLoadPowerFactor.toFixed(4)}
                        readOnly
                        disabled
                        style={disabledInputStyle}
                      />
                      <div style={{ marginTop: -2, color: '#64748b', fontSize: 12, lineHeight: 1.4 }}>
                        由无功/有功比自动换算，仅展示；负荷求解优先使用 kvar 和 q_to_p_ratio。
                      </div>

                      <PropertyGroupTitle>配储目标与变压器约束</PropertyGroupTitle>

                      <label style={labelStyle}>参与配储优化</label>
                      <select
                        value={String(booleanParam(selectedNode.params, 'optimize_storage', true))}
                        onChange={(e) => applyNodeParam('optimize_storage', e.target.value === 'true')}
                        style={inputStyle}
                      >
                        <option value="true">是</option>
                        <option value="false">否</option>
                      </select>

                      <label style={labelStyle}>反向送电限制</label>
                      <ToggleParam
                        label="允许储能向上级电网反送电"
                        params={selectedNode.params}
                        name="allow_grid_export"
                        fallback={false}
                        disabled={!selectedLoadStorageEnabled}
                        onChange={applyNodeParam}
                      />

                      <FieldLabel marker={storageControlledLabel}>变压器容量 kVA</FieldLabel>
                      <input
                        type="number"
                        disabled={!selectedLoadStorageEnabled}
                        value={numberParam(selectedNode.params, 'transformer_capacity_kva', 2000)}
                        onChange={(e) => applyNodeParam('transformer_capacity_kva', Number(e.target.value || 0))}
                        style={storageControlledInputStyle}
                      />

                      <FieldLabel marker={storageControlledLabel}>变压器功率因数下限</FieldLabel>
                      <input
                        type="number"
                        step="0.01"
                        disabled={!selectedLoadStorageEnabled}
                        value={numberParam(selectedNode.params, 'transformer_pf_limit', 0.95)}
                        onChange={(e) => applyNodeParam('transformer_pf_limit', Number(e.target.value || 0))}
                        style={storageControlledInputStyle}
                      />

                      <FieldLabel marker={storageControlledLabel}>变压器备用率</FieldLabel>
                      <input
                        type="number"
                        step="0.01"
                        disabled={!selectedLoadStorageEnabled}
                        value={numberParam(selectedNode.params, 'transformer_reserve_ratio', 0.15)}
                        onChange={(e) => applyNodeParam('transformer_reserve_ratio', Number(e.target.value || 0))}
                        style={storageControlledInputStyle}
                      />

                      <PropertyGroupTitle>自动推断（GA 搜索空间）</PropertyGroupTitle>
                      {LOAD_PANEL_READONLY_INFERRED_KEYS.map((key) => {
                        const rawValue = selectedLoadInference?.[key] ?? selectedNode?.params?.[key];
                        const v =
                          typeof rawValue === 'number' && Number.isFinite(rawValue)
                            ? String(rawValue)
                            : rawValue === undefined
                              ? '未推断'
                              : rawValue === null || rawValue === ''
                                ? '未推断'
                                : String(rawValue);
                        return (
                          <React.Fragment key={key}>
                            <label style={labelStyle}>{LOAD_PANEL_INFERRED_KEY_LABELS[key]}</label>
                            <input
                              type="text"
                              value={v === '' ? '未推断' : String(v)}
                              readOnly
                              disabled
                              style={disabledInputStyle}
                            />
                          </React.Fragment>
                        );
                      })}
                      <div style={{ marginTop: -2, color: '#64748b', fontSize: 12, lineHeight: 1.4 }}>
                        来源：{selectedLoadInference?.inference_source || '等待后端推断'}。保存拓扑后会刷新，并在构建时写入 registry。
                      </div>
                      {selectedLoadInferenceExplain.length ? (
                        <InferenceExplainTable rows={selectedLoadInferenceExplain} />
                      ) : null}
                      {selectedLoadInferenceBasis.length ? (
                        <div style={readonlyHintBoxStyle}>
                          <strong>推断依据</strong>
                          {selectedLoadInferenceBasis.map((item) => (
                            <div key={item}>• {item}</div>
                          ))}
                        </div>
                      ) : null}
                      {selectedLoadInferenceNotes.length ? (
                        <div style={readonlyWarningBoxStyle}>
                          <strong>注意</strong>
                          {selectedLoadInferenceNotes.map((item) => (
                            <div key={item}>• {item}</div>
                          ))}
                        </div>
                      ) : null}

                      <PropertyGroupTitle>调度设置</PropertyGroupTitle>

                      <label style={labelStyle}>调度模式</label>
                      <select
                        disabled={!selectedLoadStorageEnabled}
                        value={stringParam(selectedNode.params, 'dispatch_mode', 'hybrid')}
                        onChange={(e) => applyNodeParam('dispatch_mode', e.target.value)}
                        style={storageControlledInputStyle}
                      >
                        <option value="hybrid">综合优化</option>
                        <option value="price_arbitrage">电价套利</option>
                        <option value="peak_shaving">削峰填谷</option>
                      </select>

                      <label style={labelStyle}>运行模式</label>
                      <select
                        disabled={!selectedLoadStorageEnabled}
                        value={stringParam(selectedNode.params, 'run_mode', 'single_user')}
                        onChange={(e) => applyNodeParam('run_mode', e.target.value)}
                        style={storageControlledInputStyle}
                      >
                        <option value="single_user">单用户</option>
                        <option value="multi_user">多用户</option>
                      </select>

                    </>
                  ) : null}

                  <PropertyGroupTitle>高级参数</PropertyGroupTitle>

                  <textarea
                    value={nodeParamsDraft}
                    onChange={(e) => setNodeParamsDraft(e.target.value)}
                    onBlur={(e) => applyNodeParams(e.target.value)}
                    style={textareaStyle}
                  />
                  </div>

                  <div style={propertyPanelFooterStyle}>
                    <button
                      type="button"
                      style={primaryBtnStyle}
                      onClick={() => {
                        if (applyNodeParams(nodeParamsDraft)) {
                          setPropertyModalOpen(false);
                        }
                      }}
                    >
                      应用
                    </button>
                    <button type="button" style={dangerBtnStyle} onClick={removeSelectedNode}>
                      删除元件
                    </button>
                  </div>
                </>
              ) : selectedEdge ? (
                <>
                  <div style={propertyPanelBodyStyle}>
                  <div style={propertyPanelHeadingStyle}>线路：{selectedEdge.id}</div>
                  <PropertyGroupTitle>基本信息</PropertyGroupTitle>

                  <label style={labelStyle}>名称</label>
                  <input
                    value={selectedEdge.name ?? ''}
                    onChange={(e) => applyEdgeField('name', e.target.value)}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>绘图样式</label>
                  <select
                    value={selectedEdge.type}
                    onChange={(e) => applyEdgeField('type', e.target.value)}
                    style={inputStyle}
                  >
                    <option value="normal_line">常规连接线</option>
                    <option value="special_line">重点接入线</option>
                  </select>

                  <label style={labelStyle}>线路分类</label>
                  <input
                    value={selectedEdgeMeta?.categoryLabel ?? '未识别'}
                    readOnly
                    disabled
                    style={disabledInputStyle}
                  />
                  <div style={{ marginTop: -2, color: '#64748b', fontSize: 12, lineHeight: 1.4 }}>
                    线路分类会结合起终点元件、常开状态和线路型号自动识别，用于帮助阅读画布，不会改动你的拓扑连接关系。
                  </div>

                  <FieldLabel marker="必填">起点元件</FieldLabel>
                  <input
                    value={selectedEdge.from_node_id}
                    onChange={(e) => applyEdgeField('from_node_id', e.target.value)}
                    style={inputStyle}
                  />

                  <FieldLabel marker="必填">终点元件</FieldLabel>
                  <input
                    value={selectedEdge.to_node_id}
                    onChange={(e) => applyEdgeField('to_node_id', e.target.value)}
                    style={inputStyle}
                  />

                  <PropertyGroupTitle>线路模型</PropertyGroupTitle>

                  <FieldLabel marker="建议">线路型号</FieldLabel>
                  <select
                    value={stringParam(selectedEdge.params, 'linecode', 'LC_MAIN')}
                    onChange={(e) => applyEdgeLineCode(e.target.value)}
                    style={inputStyle}
                  >
                    {LINE_CODE_OPTIONS.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>

                  <FieldLabel marker="必填">潮流模型相数</FieldLabel>
                  <select value="3" onChange={() => applyEdgeParam('phases', 3)} style={inputStyle}>
                    <option value="3">三相平衡</option>
                  </select>

                  <label style={labelStyle}>线路运行状态</label>
                  <select
                    value={String(booleanParam(selectedEdge.params, 'enabled', true))}
                    onChange={(e) => applyEdgeParam('enabled', e.target.value === 'true')}
                    style={inputStyle}
                  >
                    <option value="true">启用</option>
                    <option value="false">停用</option>
                  </select>

                  <label style={labelStyle}>联络线/常开</label>
                  <select
                    value={String(booleanParam(selectedEdge.params, 'normally_open', false))}
                    onChange={(e) => applyEdgeParam('normally_open', e.target.value === 'true')}
                    style={inputStyle}
                  >
                    <option value="false">普通闭合线路</option>
                    <option value="true">常开联络线</option>
                  </select>

                  <FieldLabel marker="必填">长度 km</FieldLabel>
                  <input
                    type="number"
                    step="0.01"
                    value={numberParam(selectedEdge.params, 'length_km', 0.6)}
                    onChange={(e) => applyEdgeParam('length_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <PropertyGroupTitle>电气参数</PropertyGroupTitle>

                  <label style={labelStyle}>单位长度电阻 Ω/km</label>
                  <input
                    type="number"
                    step="0.001"
                    value={numberParam(selectedEdge.params, 'r_ohm_per_km', 0.38)}
                    onChange={(e) => applyEdgeParam('r_ohm_per_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>单位长度电抗 Ω/km</label>
                  <input
                    type="number"
                    step="0.001"
                    value={numberParam(selectedEdge.params, 'x_ohm_per_km', 0.12)}
                    onChange={(e) => applyEdgeParam('x_ohm_per_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>零序电阻 Ω/km</label>
                  <input
                    type="number"
                    step="0.001"
                    value={numberParam(selectedEdge.params, 'r0_ohm_per_km', numberParam(selectedEdge.params, 'r_ohm_per_km', 0.38))}
                    onChange={(e) => applyEdgeParam('r0_ohm_per_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>零序电抗 Ω/km</label>
                  <input
                    type="number"
                    step="0.001"
                    value={numberParam(selectedEdge.params, 'x0_ohm_per_km', numberParam(selectedEdge.params, 'x_ohm_per_km', 0.12))}
                    onChange={(e) => applyEdgeParam('x0_ohm_per_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>正序电容 nF/km</label>
                  <input
                    type="number"
                    step="0.001"
                    value={numberParam(selectedEdge.params, 'c1_nf_per_km', 0)}
                    onChange={(e) => applyEdgeParam('c1_nf_per_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <label style={labelStyle}>零序电容 nF/km</label>
                  <input
                    type="number"
                    step="0.001"
                    value={numberParam(selectedEdge.params, 'c0_nf_per_km', 0)}
                    onChange={(e) => applyEdgeParam('c0_nf_per_km', Number(e.target.value || 0))}
                    style={inputStyle}
                  />

                  <FieldLabel marker="建议">额定电流 A</FieldLabel>
                  <input
                    type="text"
                    value={
                      selectedEdgeMeta?.serviceProfile
                        ? formatCurrentDisplay(selectedEdgeMeta.serviceProfile.ratedCurrentA)
                        : String(numberParam(selectedEdge.params, 'rated_current_a', selectedEdge.type === 'special_line' ? 400 : 300))
                    }
                    readOnly={Boolean(selectedEdgeMeta?.serviceProfile)}
                    disabled={Boolean(selectedEdgeMeta?.serviceProfile)}
                    onChange={
                      selectedEdgeMeta?.serviceProfile
                        ? undefined
                        : (e) => applyEdgeParam('rated_current_a', Number(e.target.value || 0))
                    }
                    style={selectedEdgeMeta?.serviceProfile ? disabledInputStyle : inputStyle}
                  />

                  <label style={labelStyle}>应急电流 A</label>
                  <input
                    type="text"
                    value={
                      selectedEdgeMeta?.serviceProfile
                        ? formatCurrentDisplay(selectedEdgeMeta.serviceProfile.emergCurrentA)
                        : String(numberParam(selectedEdge.params, 'emerg_current_a', numberParam(selectedEdge.params, 'rated_current_a', 300) * 1.25))
                    }
                    readOnly={Boolean(selectedEdgeMeta?.serviceProfile)}
                    disabled={Boolean(selectedEdgeMeta?.serviceProfile)}
                    onChange={
                      selectedEdgeMeta?.serviceProfile
                        ? undefined
                        : (e) => applyEdgeParam('emerg_current_a', Number(e.target.value || 0))
                    }
                    style={selectedEdgeMeta?.serviceProfile ? disabledInputStyle : inputStyle}
                  />
                  {selectedEdgeMeta?.serviceProfile ? (
                    <div style={{ marginTop: -2, color: '#64748b', fontSize: 12, lineHeight: 1.5 }}>
                      {`该线路识别为用户低压接入线，系统会按用户配变容量 ${Math.round(selectedEdgeMeta.serviceProfile.transformerKva)} kVA 和接入负荷/资源规模 ${Math.round(selectedEdgeMeta.serviceProfile.resourceKva)} kVA 自动估算额定/应急电流。`}
                    </div>
                  ) : null}

                  <PropertyGroupTitle>高级参数</PropertyGroupTitle>

                  <textarea
                    value={edgeParamsDraft}
                    onChange={(e) => setEdgeParamsDraft(e.target.value)}
                    onBlur={(e) => applyEdgeParams(e.target.value)}
                    style={textareaStyle}
                  />
                  </div>

                  <div style={propertyPanelFooterStyle}>
                    <button
                      type="button"
                      style={primaryBtnStyle}
                      onClick={() => {
                        if (applyEdgeParams(edgeParamsDraft)) {
                          setPropertyModalOpen(false);
                        }
                      }}
                    >
                      应用
                    </button>
                    <button type="button" style={dangerBtnStyle} onClick={removeSelectedEdge}>
                      删除线路
                    </button>
                  </div>
                </>
              ) : (
                <div style={{ ...propertyPanelBodyStyle, color: '#6b7280' }}>请选择一个节点或一条线路。</div>
              )}
            </section>
          </div>
        </div>


        {/* Step 4: Model Preview */}
        <section style={{ ...cardStyle, marginTop: 12, padding: '12px 18px' }}>
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
            onClick={() => setModelPreviewExpanded(!modelPreviewExpanded)}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: '50%', background: '#2563eb', color: '#fff', fontSize: 11, fontWeight: 800, flexShrink: 0 }}>4</span>
            <span style={{ fontWeight: 700, fontSize: 14 }}>潮流模型预览</span>
            <span style={{ fontSize: 10, color: '#94a3b8' }}>{modelPreviewExpanded ? '▼ 点击收起' : '▶ 点击展开'}</span>
          </div>
          {modelPreviewExpanded && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 10 }}>
              <section style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h2 style={{ ...sectionTitleStyle, marginBottom: 0 }}>高级文本编辑</h2>
                  <button
                    type="button"
                    onClick={() => setJsonCollapsed((v) => !v)}
                    style={secondaryBtnStyle}
                  >
                    {jsonCollapsed ? '展开' : '收起'}
                  </button>
                </div>
                {!jsonCollapsed ? (
                  <>
                    <textarea
                      value={editorText}
                      onChange={(e) => setEditorText(e.target.value)}
                      spellCheck={false}
                      style={{
                        width: '100%',
                        minHeight: 320,
                        boxSizing: 'border-box',
                        border: '1px solid #d1d5db',
                        borderRadius: 12,
                        padding: 12,
                        fontFamily: 'Consolas, Menlo, Monaco, monospace',
                        fontSize: 12,
                        lineHeight: 1.5,
                        resize: 'vertical',
                      }}
                    />
                    <div style={{ marginTop: 12 }}>
                      <button type="button" style={primaryBtnStyle} onClick={applyJsonEditor}>
                        应用文本
                      </button>
                    </div>
                  </>
                ) : (
                  <div style={{ color: '#6b7280' }}>高级文本编辑已收起。</div>
                )}
              </section>

              <section style={cardStyle}>
                <h2 style={sectionTitleStyle}>潮流模型文件预览</h2>
                <textarea
                  value={dssPreview}
                  readOnly
                  spellCheck={false}
                  style={{
                    width: '100%',
                    minHeight: 380,
                    boxSizing: 'border-box',
                    border: '1px solid #d1d5db',
                    borderRadius: 12,
                    padding: 12,
                    fontFamily: 'Consolas, Menlo, Monaco, monospace',
                    fontSize: 12,
                    lineHeight: 1.5,
                    resize: 'vertical',
                    background: '#f8fafc',
                  }}
                />
              </section>
            </div>
          )}
        </section>

      </div>
    </div>
  );
}

function SummaryRow(props: { label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        padding: '8px 0',
        borderBottom: '1px solid #e5e7eb',
      }}
    >
      <span style={{ color: '#6b7280' }}>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function FieldLabel(props: {
  children: React.ReactNode;
  marker?: '必填' | '求解必填' | '建议' | '映射必填';
  missing?: boolean;
}) {
  const badgeStyle = props.marker === '建议' || props.marker === '求解必填' ? recommendedBadgeStyle : requiredBadgeStyle;
  return (
    <label style={fieldLabelStyle}>
      <span>{props.children}</span>
      {props.marker ? <span style={badgeStyle}>{props.marker}</span> : null}
      {props.missing ? <span style={missingBadgeStyle}>未填写</span> : null}
    </label>
  );
}

function PropertyGroupTitle(props: { children: React.ReactNode }) {
  return (
    <div style={propertySectionStyle}>
      <span style={propertySectionTitleStyle}>{props.children}</span>
    </div>
  );
}

function InferenceExplainTable(props: { rows: SearchSpaceInferenceExplainItem[] }) {
  return (
    <div style={readonlyHintBoxStyle}>
      <strong>边界解释</strong>
      <div style={inferenceExplainGridStyle}>
        {props.rows.map((row, index) => (
          <div key={row.boundary || row.boundary_name || index} style={inferenceExplainRowStyle}>
            <div style={{ fontWeight: 700, color: '#334155' }}>{row.boundary_name || row.boundary || '--'}</div>
            <div style={{ color: '#475569' }}>
              最终值 {inferenceExplainValue(row.final_value, row.unit)}；决定约束 {row.decisive_label || row.decisive_constraint || '--'}
            </div>
            <div style={{ color: '#64748b' }}>
              候选：{inferenceCandidateText(row)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function inferenceExplainValue(value: unknown, unit: unknown): string {
  const number = typeof value === 'number' && Number.isFinite(value) ? value : Number(value);
  if (!Number.isFinite(number)) return '--';
  const suffix = unit ? ` ${String(unit)}` : '';
  return `${number.toLocaleString('zh-CN', { maximumFractionDigits: 4 })}${suffix}`;
}

function inferenceCandidateText(row: SearchSpaceInferenceExplainItem): string {
  const candidates = Array.isArray(row.candidate_constraints) ? row.candidate_constraints : [];
  if (!candidates.length) return '--';
  return candidates
    .map((candidate) => {
      const label = candidate.label || candidate.constraint || '--';
      const marker = candidate.is_decisive ? '★' : '';
      return `${marker}${label} ${inferenceExplainValue(candidate.value, candidate.unit || row.unit)}`;
    })
    .join('，');
}

function NodeGlyph(props: { type: string; color: string; compact?: boolean; category?: string }) {
  const size = props.compact ? 26 : 30;
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 40 40',
    fill: 'none',
    style: { display: 'block', justifySelf: 'center' },
    'aria-hidden': true,
  } as const;

  switch (props.type) {
    case 'grid':
    case 'source':
      return (
        <svg {...common}>
          <circle cx="20" cy="20" r="16" fill="#ffffff" stroke={props.color} strokeWidth="2.6" />
          <path d="M22 7 L12 21 H19 L16 33 L29 16 H22 Z" fill={props.color} />
        </svg>
      );
    case 'transformer':
    case 'distribution_transformer':
      return (
        <svg {...common}>
          <rect x="5" y="7" width="30" height="26" rx="7" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <circle cx="16" cy="20" r="7" stroke={props.color} strokeWidth="2.2" />
          <circle cx="24" cy="20" r="7" stroke={props.color} strokeWidth="2.2" />
          <path d="M5 20 H9 M31 20 H35" stroke={props.color} strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case 'bus':
      return (
        <svg {...common}>
          <path d="M6 20 H34" stroke={props.color} strokeWidth="5" strokeLinecap="round" />
          <path d="M12 11 V29 M20 11 V29 M28 11 V29" stroke={props.color} strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case 'ring_main_unit':
      return (
        <svg {...common}>
          <rect x="8" y="6" width="24" height="28" rx="4" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <path d="M13 14 H27 M13 25 H27" stroke={props.color} strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="16" cy="20" r="3" fill={props.color} />
          <circle cx="24" cy="20" r="3" fill={props.color} />
        </svg>
      );
    case 'branch':
      return (
        <svg {...common}>
          <path d="M20 20 L20 7 M20 20 L8 31 M20 20 L32 31" stroke={props.color} strokeWidth="3" strokeLinecap="round" />
          <circle cx="20" cy="20" r="6" fill="#ffffff" stroke={props.color} strokeWidth="2.4" />
        </svg>
      );
    case 'switch':
      return (
        <svg {...common}>
          <path d="M7 24 H16 L28 13" stroke={props.color} strokeWidth="3" strokeLinecap="round" />
          <path d="M24 24 H33" stroke={props.color} strokeWidth="3" strokeLinecap="round" />
          <circle cx="16" cy="24" r="3" fill="#ffffff" stroke={props.color} strokeWidth="2" />
          <circle cx="24" cy="24" r="3" fill="#ffffff" stroke={props.color} strokeWidth="2" />
        </svg>
      );
    case 'breaker':
      return (
        <svg {...common}>
          <rect x="8" y="9" width="24" height="22" rx="4" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <path d="M12 20 H28 M16 14 L24 26" stroke={props.color} strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      );
    case 'fuse':
      return (
        <svg {...common}>
          <path d="M7 20 H13 M27 20 H33" stroke={props.color} strokeWidth="2.6" strokeLinecap="round" />
          <rect x="13" y="13" width="14" height="14" rx="3" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <path d="M17 24 L23 16" stroke={props.color} strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case 'regulator':
      return (
        <svg {...common}>
          <circle cx="20" cy="20" r="15" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <path d="M13 24 C16 12 24 12 27 24" stroke={props.color} strokeWidth="2.4" strokeLinecap="round" />
          <path d="M20 9 V14 M20 26 V31" stroke={props.color} strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case 'capacitor':
      return (
        <svg {...common}>
          <path d="M8 20 H15 M25 20 H32" stroke={props.color} strokeWidth="2.6" strokeLinecap="round" />
          <path d="M16 10 V30 M24 10 V30" stroke={props.color} strokeWidth="3" strokeLinecap="round" />
        </svg>
      );
    case 'pv':
      return (
        <svg {...common}>
          <rect x="8" y="12" width="24" height="18" rx="2" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <path d="M16 12 V30 M24 12 V30 M8 21 H32" stroke={props.color} strokeWidth="1.8" />
          <path d="M14 7 L17 4 M23 7 L26 4" stroke={props.color} strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    case 'wind':
      return (
        <svg {...common}>
          <path d="M20 21 V33" stroke={props.color} strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="20" cy="18" r="3" fill="#ffffff" stroke={props.color} strokeWidth="2" />
          <path d="M20 18 L20 6 M20 18 L31 24 M20 18 L9 24" stroke={props.color} strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      );
    case 'storage':
      return (
        <svg {...common}>
          <rect x="8" y="12" width="24" height="18" rx="3" fill="#ffffff" stroke={props.color} strokeWidth="2.2" />
          <path d="M32 18 H35 V24 H32" stroke={props.color} strokeWidth="2" strokeLinecap="round" />
          <path d="M14 21 H26 M20 15 V27" stroke={props.color} strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
    case 'load':
      if (getLoadCategory(props.category) === 'commercial') {
        return (
          <svg {...common}>
            <path d="M8 18 H32 L29 11 H11 Z" fill="#ffffff" stroke={props.color} strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M10 18 V32 H30 V18" fill="#ffffff" stroke={props.color} strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M15 32 V24 H21 V32 M12 22 H28" stroke={props.color} strokeWidth="2" strokeLinecap="round" />
            <path d="M14 15 H26" stroke={props.color} strokeWidth="2" strokeLinecap="round" />
          </svg>
        );
      }
      if (getLoadCategory(props.category) === 'residential') {
        return (
          <svg {...common}>
            <path d="M7 21 L20 9 L33 21" fill="#ffffff" stroke={props.color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M11 20 V32 H29 V20" fill="#ffffff" stroke={props.color} strokeWidth="2.2" strokeLinejoin="round" />
            <path d="M18 32 V25 H22 V32 M14 23 H18 M23 23 H27" stroke={props.color} strokeWidth="2" strokeLinecap="round" />
          </svg>
        );
      }
      return (
        <svg {...common}>
          <path d="M7 31 V17 L15 12 V17 L24 12 V17 L33 12 V31 Z" fill="#ffffff" stroke={props.color} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M12 23 H16 M19 23 H23 M26 23 H30 M12 28 H16 M19 28 H23 M26 28 H30" stroke={props.color} strokeWidth="2" strokeLinecap="round" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="20" cy="20" r="15" fill="#ffffff" stroke={props.color} strokeWidth="2.4" />
          <path d="M13 20 H27 M20 13 V27" stroke={props.color} strokeWidth="2.4" strokeLinecap="round" />
        </svg>
      );
  }
}

function ToggleParam(props: {
  label: string;
  params: Record<string, unknown> | undefined;
  name: string;
  fallback: boolean;
  disabled?: boolean;
  onChange: (name: string, value: unknown) => void;
}) {
  return (
    <label style={props.disabled ? disabledToggleRowStyle : toggleRowStyle}>
      <input
        type="checkbox"
        disabled={props.disabled}
        checked={booleanParam(props.params, props.name, props.fallback)}
        onChange={(event) => props.onChange(props.name, event.target.checked)}
      />
      <span>{props.label}</span>
    </label>
  );
}

function EconomicParamGroup(props: {
  title: string;
  control?: React.ReactNode;
  enabled?: boolean;
  children: React.ReactNode;
}) {
  const controlled = props.enabled !== undefined;
  const children = controlled
    ? React.Children.map(props.children, (child) =>
        React.isValidElement(child)
          ? React.cloneElement(child as React.ReactElement<{ disabled?: boolean; required?: boolean }>, {
              disabled: !props.enabled,
              required: props.enabled,
            })
          : child,
      )
    : props.children;

  return (
    <section style={economicGroupStyle}>
      <div style={economicGroupHeaderStyle}>
        <div style={economicGroupTitleStyle}>{props.title}</div>
        {props.control ? <div style={economicGroupControlStyle}>{props.control}</div> : null}
      </div>
      <div style={props.enabled === false ? disabledEconomicGroupFieldsStyle : economicGroupFieldsStyle}>{children}</div>
    </section>
  );
}

function EconomicNumberInput(props: {
  label: string;
  name: string;
  fallback: number;
  params: Record<string, unknown> | undefined;
  onChange: (name: string, value: unknown) => void;
  reference: string;
  step?: string;
  min?: number;
  max?: number;
  disabled?: boolean;
  required?: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <FieldLabel marker={props.required ? '必填' : undefined}>{props.label}</FieldLabel>
      <input
        type="number"
        step={props.step}
        min={props.min}
        max={props.max}
        disabled={props.disabled}
        value={numberParam(props.params, props.name, props.fallback)}
        onChange={(event) => props.onChange(props.name, Number(event.target.value || 0))}
        style={props.disabled ? disabledInputStyle : inputStyle}
      />
      <div style={props.disabled ? disabledReferenceHintStyle : referenceHintStyle}>
        {props.disabled ? '启用开关后可填写' : props.reference}
      </div>
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  background: '#ffffff',
  border: '1px solid #e5e7eb',
  borderRadius: 16,
  padding: 14,
};

const nodeNameStyle: React.CSSProperties = {
  display: 'block',
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: '#0f172a',
  fontSize: 11,
  lineHeight: 1.2,
};

const loadNodeCodeStyle: React.CSSProperties = {
  ...nodeNameStyle,
  fontSize: 13,
  lineHeight: 1.1,
  letterSpacing: 0,
};

const nodeTypeTextStyle: React.CSSProperties = {
  marginTop: 2,
  fontSize: 10,
  fontWeight: 700,
  lineHeight: 1.2,
};

const nodeDetailTextStyle: React.CSSProperties = {
  marginTop: 3,
  color: '#64748b',
  fontSize: 9,
  lineHeight: 1.2,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const candidateBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 16,
  padding: '0 4px',
  borderRadius: 999,
  background: '#dcfce7',
  color: '#166534',
  border: '1px solid #86efac',
  fontSize: 9,
  fontWeight: 700,
  flexShrink: 0,
};

const backgroundLoadBadgeStyle: React.CSSProperties = {
  ...candidateBadgeStyle,
  background: '#f1f5f9',
  color: '#475569',
  border: '1px solid #cbd5e1',
};

const economicGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr',
  gap: '10px 0',
  marginTop: 8,
  alignItems: 'start',
};

const economicGroupStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  alignSelf: 'start',
  paddingLeft: 12,
  borderLeft: '3px solid #dbeafe',
};

const economicGroupHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-start',
  alignItems: 'center',
  gap: 8,
  minHeight: 32,
};

const economicGroupTitleStyle: React.CSSProperties = {
  color: '#0f172a',
  fontSize: 14,
  fontWeight: 700,
};

const economicGroupControlStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  flexShrink: 0,
};

const economicGroupFieldsStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(4, 1fr)',
  gap: '6px 14px',
  alignItems: 'start',
};

const disabledEconomicGroupFieldsStyle: React.CSSProperties = {
  ...economicGroupFieldsStyle,
  opacity: 0.66,
};

const referenceHintStyle: React.CSSProperties = {
  marginTop: 4,
  color: '#64748b',
  fontSize: 11,
  lineHeight: 1.4,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
};

const disabledReferenceHintStyle: React.CSSProperties = {
  ...referenceHintStyle,
  color: '#94a3b8',
};

const readonlyHintBoxStyle: React.CSSProperties = {
  marginTop: 8,
  padding: 10,
  borderRadius: 8,
  border: '1px solid #dbeafe',
  background: '#eff6ff',
  color: '#1e3a8a',
  fontSize: 11,
  lineHeight: 1.55,
};

const readonlyWarningBoxStyle: React.CSSProperties = {
  ...readonlyHintBoxStyle,
  border: '1px solid #fde68a',
  background: '#fffbeb',
  color: '#92400e',
};

const inferenceExplainGridStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  marginTop: 8,
};

const inferenceExplainRowStyle: React.CSSProperties = {
  padding: 8,
  borderRadius: 6,
  background: '#ffffff',
  border: '1px solid #bfdbfe',
};

const propertyPanelStyle: React.CSSProperties = {
  ...cardStyle,
  display: 'flex',
  flexDirection: 'column',
  minHeight: 0,
  height: '100%',
  boxSizing: 'border-box',
  overflow: 'hidden',
};

const fullscreenCanvasStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 12,
  zIndex: 70,
  background: '#ffffff',
  border: '1px solid #dbe3ef',
  borderRadius: 16,
  padding: 14,
  boxShadow: '0 24px 70px rgba(15,23,42,0.22)',
};

const modalBackdropStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 80,
  background: 'rgba(15,23,42,0.38)',
};

const propertyModalStyle: React.CSSProperties = {
  position: 'fixed',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  width: 'min(640px, calc(100vw - 32px))',
  maxHeight: '86vh',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  zIndex: 90,
  background: '#ffffff',
  border: '1px solid #dbe3ef',
  borderRadius: 16,
  padding: 18,
  boxSizing: 'border-box',
  boxShadow: '0 24px 70px rgba(15,23,42,0.28)',
};

const propertyPanelBodyStyle: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflowY: 'auto',
  overscrollBehavior: 'contain',
  paddingRight: 4,
};

const propertyPanelHeadingStyle: React.CSSProperties = {
  fontWeight: 700,
  marginBottom: 10,
  color: '#111827',
};

const propertySectionStyle: React.CSSProperties = {
  padding: '12px 0 14px',
  borderTop: '1px solid #e5e7eb',
};

const propertySectionTitleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 800,
  color: '#0f172a',
  marginBottom: 8,
};

const propertyPanelFooterStyle: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  flexWrap: 'wrap',
  flexShrink: 0,
  marginTop: 12,
  paddingTop: 12,
  borderTop: '1px solid #e5e7eb',
};

const requiredLegendStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexWrap: 'wrap',
  flexShrink: 0,
  marginBottom: 10,
  color: '#64748b',
  fontSize: 11,
  lineHeight: 1.4,
};

const requiredBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 18,
  padding: '0 6px',
  borderRadius: 999,
  border: '1px solid #fecaca',
  background: '#fef2f2',
  color: '#b91c1c',
  fontSize: 11,
  fontWeight: 700,
};

const recommendedBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 18,
  padding: '0 6px',
  borderRadius: 999,
  border: '1px solid #fde68a',
  background: '#fffbeb',
  color: '#92400e',
  fontSize: 11,
  fontWeight: 700,
};

const missingBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 18,
  padding: '0 6px',
  borderRadius: 999,
  border: '1px solid #f87171',
  background: '#fee2e2',
  color: '#991b1b',
  fontSize: 11,
  fontWeight: 700,
};

const sectionTitleStyle: React.CSSProperties = {
  margin: '0 0 12px 0',
  fontSize: 18,
};

const paletteBtnStyle: React.CSSProperties = {
  width: '100%',
  textAlign: 'left',
  padding: '9px 10px',
  borderRadius: 10,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  fontWeight: 600,
  cursor: 'pointer',
};

const paletteGroupTitleStyle: React.CSSProperties = {
  marginTop: 6,
  color: '#64748b',
  fontSize: 12,
  fontWeight: 800,
};

const fullscreenPaletteStyle: React.CSSProperties = {
  position: 'absolute',
  right: 18,
  top: 66,
  zIndex: 6,
  width: 190,
  maxHeight: 'calc(100vh - 112px)',
  display: 'grid',
  gridTemplateRows: 'auto minmax(0, 1fr)',
  border: '1px solid #dbe3ef',
  borderRadius: 12,
  background: 'rgba(255,255,255,0.96)',
  boxShadow: '0 16px 40px rgba(15,23,42,0.18)',
  overflow: 'hidden',
};

const fullscreenPaletteTitleStyle: React.CSSProperties = {
  padding: '10px 12px',
  borderBottom: '1px solid #e5e7eb',
  color: '#0f172a',
  fontSize: 14,
  fontWeight: 800,
};

const fullscreenPaletteBodyStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  minHeight: 0,
  overflowY: 'auto',
  padding: 10,
};

const fullscreenLineToolStyle: React.CSSProperties = {
  display: 'grid',
  gap: 8,
  paddingBottom: 10,
  marginBottom: 2,
  borderBottom: '1px solid #e5e7eb',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid #111827',
  background: '#0f172a',
  color: '#ffffff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid #d1d5db',
  background: '#ffffff',
  color: '#111827',
  textDecoration: 'none',
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerBtnStyle: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 10,
  border: '1px solid #fca5a5',
  background: '#ffffff',
  color: '#dc2626',
  fontWeight: 700,
  cursor: 'pointer',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12,
  color: '#6b7280',
  marginTop: 10,
  marginBottom: 6,
};

const fieldLabelStyle: React.CSSProperties = {
  ...labelStyle,
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexWrap: 'wrap',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 10,
  padding: '9px 10px',
  fontSize: 13,
};

const disabledInputStyle: React.CSSProperties = {
  ...inputStyle,
  background: '#f8fafc',
  color: '#94a3b8',
  cursor: 'not-allowed',
};

const missingRequiredInputStyle: React.CSSProperties = {
  ...inputStyle,
  borderColor: '#f87171',
  background: '#fff7f7',
};

const toggleRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  minHeight: 32,
  color: '#374151',
  fontSize: 13,
};

const disabledToggleRowStyle: React.CSSProperties = {
  ...toggleRowStyle,
  color: '#94a3b8',
  cursor: 'not-allowed',
};

const textareaStyle: React.CSSProperties = {
  width: '100%',
  minHeight: 110,
  boxSizing: 'border-box',
  border: '1px solid #d1d5db',
  borderRadius: 10,
  padding: '9px 10px',
  fontSize: 12,
  fontFamily: 'Consolas, Menlo, Monaco, monospace',
  resize: 'vertical',
  overscrollBehavior: 'contain',
};

const successStyle: React.CSSProperties = {
  background: '#f0fdf4',
  border: '1px solid #bbf7d0',
  color: '#166534',
  borderRadius: 12,
  padding: 12,
  marginBottom: 12,
};
