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
    population_size?: number;
    feasible_count?: number;
    archive_size?: number;
    best_npv_yuan?: number | null;
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
