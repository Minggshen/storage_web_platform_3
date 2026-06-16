export type StepPayload = {
  key: string;
  label: string;
  status: string;
  detail?: string | null;
  route?: string;
  counts?: Record<string, unknown>;
};

export type DashboardPayload = {
  project_id: string;
  project_name: string;
  description?: string | null;
  node_count?: number;
  edge_count?: number;
  load_node_count?: number;
  runtime_bound_load_count?: number;
  has_tariff?: boolean;
  has_device_library?: boolean;
  build_ready?: boolean;
  build_manifest_exists?: boolean;
  latest_solver_status?: string | null;
  latest_summary?: Record<string, unknown>;
  steps?: StepPayload[];
};

export type BuildPreviewResponse = {
  success?: boolean;
  project_id?: string;
  ready_for_build: boolean;
  warnings: string[];
  errors: string[];
  dss_compile_ready?: boolean;
};

export type BuildInferenceRow = Record<string, unknown>;

export type BuildInferenceResponse = {
  success?: boolean;
  project_id?: string;
  rows: BuildInferenceRow[];
};

export type BuildArtifact = {
  category: string;
  relative_path: string;
  absolute_path?: string;
  exists?: boolean;
};

export type BuildManifestSummary = {
  project_id: string;
  project_name?: string;
  workspace_dir?: string;
  inputs_dir?: string;
  artifact_count?: number;
  warnings?: number;
  errors?: number;
  dss_dir?: string;
  dss_master_path?: string;
  dss_master_preview?: string;
  dss_compile?: {
    warnings?: string[];
    generated_files?: string[];
  };
  [key: string]: unknown;
};

export type BuildManifestResponse = {
  success: boolean;
  summary: BuildManifestSummary;
  artifacts: BuildArtifact[];
};

export type TopologyNodeRecord = {
  id: string;
  type: string;
  name: string;
  voltageLevelKv?: number;
  transformerCapacityKva?: number | null;
  transformerPfLimit?: number | null;
  transformerReserveRatio?: number | null;
  qToPRatio?: number | null;
  [key: string]: unknown;
};

export type TopologyEdgeRecord = {
  id: string;
  type: string;
  name?: string;
  fromNodeId?: string;
  toNodeId?: string;
  from_node_id?: string;
  to_node_id?: string;
  [key: string]: unknown;
};

export type SolverTask = {
  task_id: string;
  project_id?: string;
  task_name?: string;
  status?: string;
  message?: string;
  return_code?: number | null;
  started_at?: string | number | null;
  completed_at?: string | number | null;
  stdout_log?: string;
  stderr_log?: string;
  stdout_text?: string;
  stderr_text?: string;
  stdout_encoding?: string | null;
  stderr_encoding?: string | null;
  stdout_size?: number;
  stderr_size?: number;
  health_status?: string | null;
  health_issue_count?: number | null;
  health_warning_count?: number | null;
  health_critical_count?: number | null;
  progress_hint?: {
    percent?: number;
    label?: string;
    detail?: string;
    source?: string;
  };
  metadata?: Record<string, unknown>;
};

export type EngineDiagnosticsScenario = {
  scenario?: string;
  cache_stats?: {
    cache_size?: number;
    cache_hits?: number;
    cache_misses?: number;
    hit_rate?: number;
  };
  constraint_breakdown?: {
    hard?: number;
    medium?: number;
    soft?: number;
    raw?: Record<string, number | null | undefined>;
  };
  population_history?: Array<{
    generation?: number;
    global_generation?: number;
    local_generation?: number;
    local_generations?: number;
    strategy_id?: string | null;
    strategy_index?: number | null;
    strategy_ordinal?: number | null;
    strategy_total?: number | null;
    population_size?: number;
    feasible_count?: number;
    archive_size?: number;
    best_npv_yuan?: number | null;
    generation_wall_time_s?: number | null;
    evaluator_eval_count?: number | null;
  }>;
};

export type EngineDiagnosticsPayload =
  | EngineDiagnosticsScenario
  | {
      scenarios?: EngineDiagnosticsScenario[];
      scenario_count?: number;
    };

export type SolverSummaryResponse = {
  success?: boolean;
  project_id: string;
  summary_rows: Record<string, unknown>[];
  best_result_summary: Record<string, unknown>;
  overall_best_schemes: Record<string, unknown>[];
  engine_diagnostics?: EngineDiagnosticsPayload | null;
};

export type ResultChartPoint = Record<string, string | number | boolean | null | undefined>;

export type ResultFeasibilityDiagnostics = {
  summary?: Record<string, string | number | boolean | null | undefined>;
  violations?: ResultChartPoint[];
  candidate_status?: ResultChartPoint[];
  candidate_violations?: ResultChartPoint[];
};

export type ResultChartsResponse = {
  success?: boolean;
  project_id: string;
  latest_task?: {
    task_id?: string | null;
    status?: string | null;
    started_at?: string | number | null;
    completed_at?: string | number | null;
  };
  selected_case?: string | null;
  warnings?: string[];
  source_files?: Record<string, string | null>;
  diagnostics?: Record<string, unknown>;
  charts?: {
    feasibility_diagnostics?: ResultFeasibilityDiagnostics;
    monthly_revenue?: ResultChartPoint[];
    representative_day?: {
      dayIndex?: number | null;
      rows?: ResultChartPoint[];
    };
    daily_operation?: ResultChartPoint[];
    yearly_soc?: ResultChartPoint[];
    cashflow?: ResultChartPoint[];
    capital_breakdown?: ResultChartPoint[];
    annual_value_breakdown?: ResultChartPoint[];
    financial_metrics?: ResultChartPoint[];
    pareto?: ResultChartPoint[];
    pareto_frontier?: ResultChartPoint[];
    investment_economics?: ResultChartPoint[];
    investment_economics_summary?: ResultChartPoint;
    degradation_soh?: ResultChartPoint[];
    lcos?: {
      summary?: ResultChartPoint;
      components?: ResultChartPoint[];
      annual?: ResultChartPoint[];
    };
    optimization_history?: ResultChartPoint[];
    storage_impact?: ResultChartPoint[];
    network_constraints?: {
      daily?: ResultChartPoint[];
      monthly?: ResultChartPoint[];
      summary?: ResultChartPoint[];
    };
    line_capacity?: ResultChartPoint[];
    network_topology?: {
      nodes?: ResultChartPoint[];
      edges?: ResultChartPoint[];
      summary?: ResultChartPoint[];
      warnings?: string[];
      selectedNodeId?: string | null;
      dataQuality?: string;
    };
    deliverables?: Record<string, unknown>;
  };
};

export type ResultFileItem = {
  name: string;
  relative_path: string;
  absolute_path?: string;
  size_bytes?: number;
  suffix?: string;
  group?: string;
};

export type ResultFilesResponse = {
  success?: boolean;
  project_id: string;
  groups?: Record<string, ResultFileItem[]>;
  files: ResultFileItem[];
  counts?: Record<string, number>;
};

export type ResultFilePreviewResponse = {
  success: boolean;
  project_id: string;
  group?: string | null;
  relative_path: string;
  file_name: string;
  type: 'csv' | 'text' | 'image';
  header?: string[];
  rows?: string[][];
  row_count?: number;
  total_rows?: number;
  content?: string;
  encoding?: string | null;
};

// ---- Report Payload types ----

export type ReportTaskMeta = {
  task_id?: string | null;
  status?: string | null;
  started_at?: string | number | null;
  completed_at?: string | number | null;
  selected_case?: string | null;
};

export type ReportSourceFile = {
  relative_path: string;
  group?: string | null;
};

export type ReportAssumptions = {
  tariff_year?: number | null;
  discount_rate?: number | null;
  project_life_years?: number | null;
  soc_min?: number | null;
  soc_max?: number | null;
  opendss_enabled?: boolean | null;
  opendss_coverage_hours?: number | null;
  initial_soc?: number | null;
  terminal_soc_mode?: string | null;
  safety_economy_tradeoff?: number | null;
};

export type ReportLoadProfile = {
  peak_kw?: number | null;
  valley_kw?: number | null;
  annual_mean_kw?: number | null;
  mean_daily_energy_kwh?: number | null;
  load_factor?: number | null;
  target_node_name?: string | null;
  target_node_id?: string | null;
};

export type ReportMonthlyRevenuePoint = {
  month?: number;
  arbitrageRevenueWan?: number | null;
  demandSavingWan?: number | null;
  serviceNetRevenueWan?: number | null;
  capacityRevenueWan?: number | null;
  lossReductionRevenueWan?: number | null;
  penaltyCostWan?: number | null;
  netCashflowWan?: number | null;
};

export type ReportRepresentativeDayChart = {
  dayIndex?: number | null;
  rows?: Record<string, unknown>[];
};

export type ReportCashflowChartPoint = {
  year?: number;
  revenueWan?: number | null;
  operatingRevenueWan?: number | null;
  arbitrageRevenueWan?: number | null;
  demandSavingWan?: number | null;
  auxiliaryServiceRevenueWan?: number | null;
  capacityRevenueWan?: number | null;
  lossReductionRevenueWan?: number | null;
  operatingCostWan?: number | null;
  degradationCostWan?: number | null;
  omCostWan?: number | null;
  replacementCostWan?: number | null;
  salvageValueWan?: number | null;
  netCashflowWan?: number | null;
  discountedNetCashflowWan?: number | null;
  cumulativeDiscountedWan?: number | null;
  cumulativeUndiscountedWan?: number | null;
};

export type ReportCapitalBreakdownItem = {
  name: string;
  valueWan?: number | null;
};

export type ReportAnnualValueBreakdownItem = {
  name: string;
  valueWan?: number | null;
};

export type ReportFinancialMetricItem = {
  name: string;
  value?: number | null;
  unit?: string | null;
};

export type ReportParetoCandidate = {
  index?: number;
  strategyId?: string | null;
  ratedPowerKw?: number | null;
  ratedEnergyKwh?: number | null;
  durationH?: number | null;
  npvWan?: number | null;
  initialInvestmentWan?: number | null;
  paybackYears?: number | null;
  annualCycles?: number | null;
  feasible?: boolean | null;
  totalViolation?: number | null;
  paretoFrontier?: boolean | null;
  frontierOrder?: number | null;
  recommendedCandidate?: boolean | null;
  objectiveBest?: boolean | null;
};

export type ReportDegradationSohPoint = {
  year?: number | null;
  batterySoh?: number | null;
  batterySohPct?: number | null;
  capacityFactor?: number | null;
  capacityFactorPct?: number | null;
  degradationCostWan?: number | null;
  replacementCostWan?: number | null;
  replacementEvent?: boolean | null;
  annualThroughputKwh?: number | null;
  annualCycles?: number | null;
};

export type ReportLcosChart = {
  summary?: {
    lcosYuanPerKwh?: number | null;
    totalCostWan?: number | null;
    totalThroughputMwh?: number | null;
    averageRevenueYuanPerKwh?: number | null;
  } | null;
  components?: ReportAnnualValueBreakdownItem[];
  annual?: Record<string, unknown>[];
};

export type ReportOptimizationHistoryChart = {
  total_generations?: number;
  best_npv_wan?: number | null;
  best_generation?: number | null;
  final_feasible_count?: number | null;
  final_population_size?: number | null;
  sampled_points?: Record<string, unknown>[];
};

export type ReportNetworkConstraintsChart = {
  monthly?: Record<string, unknown>[];
  summary?: Record<string, unknown>[];
};

export type ReportFeasibilityDiagnosticsChart = {
  summary?: Record<string, unknown> | null;
  violations?: Record<string, unknown>[];
  candidate_status?: Record<string, unknown>[];
  candidate_violations?: Record<string, unknown>[];
};

export type ReportCharts = {
  monthly_revenue?: ReportMonthlyRevenuePoint[];
  representative_day?: ReportRepresentativeDayChart | null;
  cashflow?: ReportCashflowChartPoint[];
  capital_breakdown?: ReportCapitalBreakdownItem[];
  annual_value_breakdown?: ReportAnnualValueBreakdownItem[];
  financial_metrics?: ReportFinancialMetricItem[];
  pareto?: ReportParetoCandidate[];
  pareto_frontier?: ReportParetoCandidate[];
  investment_economics?: Record<string, unknown>[];
  investment_economics_summary?: Record<string, unknown> | null;
  degradation_soh?: ReportDegradationSohPoint[];
  lcos?: ReportLcosChart | null;
  optimization_history?: ReportOptimizationHistoryChart | null;
  network_constraints?: ReportNetworkConstraintsChart | null;
  feasibility_diagnostics?: ReportFeasibilityDiagnosticsChart | null;
};

export type ReportCandidateComparison = {
  recommended?: Record<string, unknown> | null;
  alternatives?: Record<string, unknown>[];
};

export type ReportDataQuality = {
  missing_data_flags?: string[];
  degraded_calculations?: string[];
  opendss_enabled?: boolean;
  trace_completeness?: string | null;
};

export type ReportProjectMeta = {
  project_name: string;
  description?: string | null;
  created_at?: string | null;
  version?: string;
  node_count?: number;
  edge_count?: number;
  load_node_count?: number;
  has_tariff?: boolean;
  tariff_year?: number | null;
};

export type ReportDeviceSpec = {
  vendor?: string | null;
  model?: string | null;
  series_name?: string | null;
  device_family?: string | null;
  battery_chemistry?: string | null;
  rated_power_kw?: number | null;
  rated_energy_kwh?: number | null;
  usable_energy_kwh_at_fat?: number | null;
  duration_hour?: number | null;
  dc_voltage_range_v?: string | null;
  ac_grid_voltage_v?: string | null;
  cooling_type?: string | null;
  fire_detection?: string | null;
  fire_suppression?: string | null;
  safety_level?: string | null;
  cycle_life?: number | null;
  soc_min?: number | null;
  soc_max?: number | null;
  efficiency_pct?: number | null;
  ip_system?: string | null;
  corrosion_grade?: string | null;
  install_mode?: string | null;
  dimension_w_mm?: number | null;
  dimension_d_mm?: number | null;
  dimension_h_mm?: number | null;
  weight_kg?: number | null;
  price_yuan_per_wh?: number | null;
  energy_unit_price_yuan_per_kwh?: number | null;
  power_related_capex_yuan_per_kw?: number | null;
  communication_protocol?: string | null;
  supports_black_start?: boolean | null;
  supports_offgrid_microgrid?: boolean | null;
};

export type ReportConfiguration = {
  target_id?: string | null;
  target_bus?: string | null;
  strategy_id?: string | null;
  strategy_name?: string | null;
  rated_power_kw?: number | null;
  rated_energy_kwh?: number | null;
  duration_h?: number | null;
  capacity_factor?: number | null;
  background_load_policy?: string | null;
};

export type ReportOperation = {
  annual_equivalent_full_cycles?: number | null;
  annual_battery_throughput_kwh?: number | null;
  capacity_factor?: number | null;
};

export type ReportRevenueBreakdown = {
  arbitrage?: number | null;
  demand_saving?: number | null;
  capacity?: number | null;
  loss_reduction?: number | null;
  auxiliary_service?: number | null;
};

export type ReportCostBreakdown = {
  degradation?: number | null;
  o_and_m?: number | null;
  replacement?: number | null;
  transformer_penalty?: number | null;
  voltage_penalty?: number | null;
};

export type ReportFinancialCore = {
  npv_yuan?: number | null;
  irr?: number | null;
  simple_payback_years?: number | null;
  discounted_payback_years?: number | null;
  initial_investment_yuan?: number | null;
  annualized_net_cashflow_yuan?: number | null;
  lcoe_yuan_per_kwh?: number | null;
  roi_pct?: number | null;
  revenue_breakdown?: ReportRevenueBreakdown | null;
  cost_breakdown?: ReportCostBreakdown | null;
};

export type ReportAuditLedgerItem = {
  name: string;
  category: string;
  amount_yuan?: number | null;
  quantity?: number | null;
  unit_price?: number | null;
  anomaly?: string | null;
};

export type ReportAuditAnomaly = {
  item: string;
  field: string;
  level: string;
  message: string;
};

export type ReportCashflowRow = {
  year?: number | null;
  revenue_yuan?: number | null;
  op_cost_yuan?: number | null;
  net_cashflow_yuan?: number | null;
  cumulative_undiscounted_yuan?: number | null;
  discounted_net_yuan?: number | null;
  cumulative_discounted_yuan?: number | null;
};

export type ReportFinancial = {
  core?: ReportFinancialCore | null;
  audit_ledger_items?: ReportAuditLedgerItem[];
  audit_ledger_anomalies?: ReportAuditAnomaly[];
  audit_ledger_item_count?: number;
  audit_ledger_anomaly_count?: number;
  cashflow_table?: ReportCashflowRow[];
};

export type ReportNetworkImpact = {
  target_area_conclusion?: Record<string, unknown> | null;
  attribution_summary?: Record<string, unknown> | null;
  risk_classification?: Record<string, unknown>[];
  voltage_top_risks?: Record<string, unknown>[];
  line_top_risks?: Record<string, unknown>[];
  transformer_top_risks?: Record<string, unknown>[];
  data_quality?: Record<string, unknown> | null;
  baseline?: Record<string, unknown> | null;
  with_storage?: Record<string, unknown> | null;
  delta?: Record<string, unknown> | null;
};

export type ReportHealthIssue = {
  code?: string;
  message?: string;
  severity?: string;
  level?: string;
  reason?: string;
  impact?: string;
  suggestion?: string;
  related_section?: string;
};

export type ReportRunHealth = {
  status?: string;
  total_issues?: number;
  warning_count?: number;
  critical_count?: number;
  issues?: ReportHealthIssue[];
};

export type ReportPayload = {
  project_meta: ReportProjectMeta;
  devices: ReportDeviceSpec[];
  configuration?: ReportConfiguration | null;
  operation?: ReportOperation | null;
  financial?: ReportFinancial | null;
  network_impact?: ReportNetworkImpact | null;
  run_health?: ReportRunHealth | null;
  warnings?: string[];
  task_meta?: ReportTaskMeta | null;
  source_files?: ReportSourceFile[];
  assumptions?: ReportAssumptions | null;
  load_profile?: ReportLoadProfile | null;
  charts?: ReportCharts | null;
  candidate_comparison?: ReportCandidateComparison | null;
  data_quality?: ReportDataQuality | null;
  generated_at?: string;
};
