import type { LoadCategory, NodeVisualSpec } from './topologyTypes';

export const LOAD_CATEGORY_VISUALS: Record<LoadCategory, NodeVisualSpec & { label: string }> = {
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

export const EMPTY_TOPOLOGY_TEXT = `{
  "nodes": [],
  "edges": [],
  "economic_parameters": {}
}`;

export const CANVAS_WIDTH = 2200;
export const CANVAS_HEIGHT = 1400;
export const TOPOLOGY_WORKBENCH_HEIGHT = 860;
export const NODE_WIDTH = 128;
export const NODE_HEIGHT = 64;
export const DEFAULT_LINE_TYPE = 'normal_line' as const;
export const DEFAULT_LINE_CODE = 'LC_MAIN';
export const NODE_REPEL_PADDING = 10;

export const LOAD_PANEL_REMOVED_PARAM_KEYS = [
  'description',
  'voltage_level_kv',
  'pv_capacity_kw',
  'grid_interconnection_limit_kw',
];

export const LOAD_PANEL_READONLY_INFERRED_KEYS = [
  'search_power_min_kw',
  'search_duration_min_h',
  'search_duration_max_h',
  'device_power_max_kw',
] as const;

export const LOAD_PANEL_INFERRED_KEY_LABELS: Record<(typeof LOAD_PANEL_READONLY_INFERRED_KEYS)[number], string> = {
  search_power_min_kw: 'GA 搜索功率下限 kW',
  search_duration_min_h: 'GA 搜索时长下限 h',
  search_duration_max_h: 'GA 搜索时长上限 h',
  device_power_max_kw: '设备功率上限 kW',
};

export const TRANSFORMER_NODE_TYPES = new Set(['transformer', 'distribution_transformer']);
export const BUS_EQUIPMENT_NODE_TYPES = new Set(['bus', 'ring_main_unit', 'branch', 'switch', 'breaker', 'fuse', 'regulator']);
export const RESOURCE_NODE_TYPES = new Set(['pv', 'wind', 'storage']);

export const NODE_ADVANCED_PARAM_KEYS: Record<string, readonly string[]> = {
  grid: ['base_kv', 'pu', 'phases', 'source_bus', 'dss_bus_name', 'mvasc3', 'mvasc1', 'x1r1', 'x0r0'],
  source: ['base_kv', 'pu', 'phases', 'source_bus', 'dss_bus_name', 'mvasc3', 'mvasc1', 'x1r1', 'x0r0'],
  transformer: [
    'rated_kva', 'voltage_level_kv', 'primary_voltage_kv', 'primary_bus_name', 'dss_bus_name',
    'secondary_bus_name', 'primary_conn', 'secondary_conn', 'xhl_percent', 'percent_r', 'tap', 'phases',
  ],
  distribution_transformer: [
    'enabled', 'rated_kva', 'primary_voltage_kv', 'voltage_level_kv', 'primary_bus_name',
    'dss_bus_name', 'secondary_bus_name', 'primary_conn', 'secondary_conn', 'xhl_percent',
    'percent_r', 'tap', 'phases',
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
  storage: ['dss_name', 'enabled', 'dss_bus_name', 'voltage_level_kv', 'phases', 'rated_kw', 'rated_kwh', 'initial_soc_pct', 'reserve_soc_pct'],
  load: [
    'enabled', 'node_id', 'dss_bus_name', 'dss_load_name', 'target_kv_ln', 'phases', 'category',
    'remarks', 'model_year', 'design_kw', 'kvar', 'q_to_p_ratio', 'connection', 'model',
    'optimize_storage', 'allow_grid_export', 'transformer_capacity_kva', 'transformer_pf_limit',
    'transformer_reserve_ratio', 'dispatch_mode', 'run_mode',
  ],
};

export const NODE_HIDDEN_PERSISTED_PARAM_KEYS: Record<string, readonly string[]> = {
  distribution_transformer: ['transformer_role', 'is_distribution_transformer', 'role'],
  load: ['storage_placeholder', 'storage_placeholder_kw', 'storage_placeholder_kwh', 'storage_name'],
};

export const EDGE_ADVANCED_PARAM_KEYS = [
  'linecode', 'phases', 'enabled', 'normally_open', 'length_km', 'units',
  'r_ohm_per_km', 'x_ohm_per_km', 'r0_ohm_per_km', 'x0_ohm_per_km',
  'c1_nf_per_km', 'c0_nf_per_km', 'rated_current_a', 'emerg_current_a',
] as const;

export const ECONOMIC_DEFAULT_PARAMS: Record<string, unknown> = {
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
  integration_markup_ratio: 0.15,
  safety_markup_ratio: 0.02,
  other_capex_yuan: 0,
  battery_capex_share: 0.6,
  calendar_life_years: 20,
  calendar_fade_share: 0.15,
  replacement_cost_ratio: 0.6,
  replacement_year_override: 0,
  replacement_trigger_soh: 0.7,
  replacement_reset_soh: 0.95,
  demand_charge_yuan_per_kw_month: 48,
  daily_demand_shadow_yuan_per_kw: 48,
  voltage_penalty_coeff_yuan: 0,
};

export const ECONOMIC_PARAM_KEYS = new Set(Object.keys(ECONOMIC_DEFAULT_PARAMS));

export const DEPRECATED_DEVICE_ECONOMIC_PARAM_KEYS = new Set([
  'power_related_capex_yuan_per_kw',
  'degradation_cost_yuan_per_kwh_throughput',
  'cycle_life_efc',
  'annual_cycle_limit',
  'annual_fixed_om_yuan_per_kw_year',
  'annual_variable_om_yuan_per_kwh',
]);

export const LINE_CODE_OPTIONS = [
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

export const LINE_STROKE_BY_CODE: Record<string, string> = {
  LC_MAIN: '#1d4ed8',
  LC_BRANCH: '#0f766e',
  LC_CABLE: '#2563eb',
  LC_LIGHT: '#64748b',
};

export const SERVICE_LINE_LINECODE = 'LC_CABLE';
export const SERVICE_LINE_DEFAULT_LENGTH_KM = 0.005;
export const SERVICE_LINE_RESOURCE_MARGIN = 1.1;
export const SERVICE_LINE_EMERGENCY_MARGIN = 1.2;
export const SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN = 1.25;
export const SERVICE_LINE_MIN_RATED_A = 1;

export const WIRE_DATA_CU: Array<{name: string; rac: number; normamps: number}> = [
  { name: '250_CU',  rac: 0.159692, normamps: 540  },
  { name: '350_CU',  rac: 0.114643, normamps: 660  },
  { name: '400_CU',  rac: 0.100662, normamps: 730  },
  { name: '500_CU',  rac: 0.080778, normamps: 840  },
  { name: '600_CU',  rac: 0.062323, normamps: 900  },
  { name: '750_CU',  rac: 0.055302, normamps: 1090 },
  { name: '1000_CU', rac: 0.042875, normamps: 1300 },
];

export const WIRE_XR_RATIO = 0.46;
export const SERVICE_LINE_LOW_Z_CURRENT_THRESHOLD_A = 1500.0;

export const LINE_LEGEND_ITEMS: Array<{ label: string; stroke: string; dash?: string }> = [
  { label: '用户低压接入线（自动）', stroke: '#d97706' },
  { label: '常开联络线', stroke: '#7c3aed', dash: '8 6' },
  { label: '10kV主干线', stroke: LINE_STROKE_BY_CODE.LC_MAIN },
  { label: '10kV分支线', stroke: LINE_STROKE_BY_CODE.LC_BRANCH },
  { label: '10kV电缆/大载流线路', stroke: LINE_STROKE_BY_CODE.LC_CABLE },
  { label: '末端轻载支线', stroke: LINE_STROKE_BY_CODE.LC_LIGHT },
];
