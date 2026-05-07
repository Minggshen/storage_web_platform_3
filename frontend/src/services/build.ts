import { http } from './http';

export type DssStructuralCheckRow = {
  name?: string;
  status?: string;
  detail?: string;
};

export type DssStructuralChecks = {
  passed?: boolean;
  errors?: string[];
  warnings?: string[];
  checks?: DssStructuralCheckRow[];
};

export type DssOpenDssProbe = {
  mode?: string;
  attempted?: boolean;
  status?: string;
  engine?: string;
  compile_succeeded?: boolean;
  solve_executed?: boolean;
  solve_converged?: boolean;
  circuit_name?: string;
  bus_count?: number;
  line_count?: number;
  load_count?: number;
  compile_result?: string;
  solve_result?: string;
  message?: string;
  stderr_tail?: string;
};

export type DssCompileSummary = {
  structural_checks?: DssStructuralChecks;
  opendss_probe?: DssOpenDssProbe;
  runtime_injection_contract?: Record<string, unknown>;
  topology_case_summary?: Record<string, unknown>;
  line_summary?: Array<{
    id?: string;
    name?: string;
    type?: string;
    from_bus?: string;
    to_bus?: string;
    linecode?: string;
    length_km?: number;
    normamps?: number;
    emergamps?: number;
    enabled?: boolean;
    normally_open?: boolean;
    auto_service_line?: boolean;
    service_secondary_kv?: number | null;
    service_transformer_kva?: number | null;
    service_resource_kva?: number | null;
    service_transformer_current_a?: number | null;
    service_resource_current_a?: number | null;
    service_equivalent_mode?: string | null;
    service_cable_name?: string | null;
    service_cable_parallel?: number | null;
    service_equivalent_r1_ohm_per_km?: number | null;
    service_equivalent_x1_ohm_per_km?: number | null;
    service_parallel_note?: string | null;
    line_voltage_kv?: number | null;
    downstream_transformer_kva?: number | null;
    downstream_load_kva?: number | null;
    downstream_apparent_kva?: number | null;
    estimated_required_current_a?: number | null;
    recommended_current_a?: number | null;
    recommended_linecode?: string | null;
    capacity_check_status?: string | null;
    capacity_check_message?: string | null;
  }>;
  [key: string]: unknown;
};

export type SearchSpaceInferenceRow = {
  node_id: string;
  node_name?: string;
  node_type?: string;
  transformer_capacity_kva?: number | null;
  transformer_pf_limit?: number | null;
  transformer_reserve_ratio?: number | null;
  grid_interconnection_limit_kw?: number | null;
  peak_kw?: number | null;
  valley_kw?: number | null;
  annual_mean_kw?: number | null;
  mean_daily_energy_kwh?: number | null;
  transformer_limit_kw?: number | null;
  search_power_min_kw?: number | null;
  device_power_max_kw?: number | null;
  search_duration_min_h?: number | null;
  search_duration_max_h?: number | null;
  inference_source?: string;
  basis?: string[];
  notes?: string[];
  explain?: SearchSpaceInferenceExplainItem[];
};

export type SearchSpaceInferenceExplainItem = {
  boundary?: string;
  boundary_name?: string;
  unit?: string;
  final_value?: number | null;
  decisive_constraint?: string;
  decisive_label?: string;
  candidate_constraints?: Array<{
    constraint?: string;
    label?: string;
    source?: string;
    value?: number | null;
    unit?: string;
    is_decisive?: boolean;
  }>;
  description?: string;
};

export type SearchSpaceInferenceResponse = {
  success: boolean;
  project_id: string;
  rows: SearchSpaceInferenceRow[];
};

export type BuildPreviewResponse = {
  success: boolean;
  summary: {
    project_id: string;
    project_name: string;
    ready_for_build: boolean;
    warnings: string[];
    errors: string[];
    node_count: number;
    edge_count: number;
    grid_count?: number;
    transformer_count?: number;
    load_count?: number;
    active_edge_count?: number;
    disconnected_count?: number;
  };
  preview: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
  };
};

export type BuildManifest = {
  success: boolean;
  project_id: string;
  project_name: string;
  build_dir: string;
  inputs_dir: string;
  ready_for_build: boolean;
  warnings: string[];
  errors: string[];
  topology_summary: {
    node_count: number;
    edge_count: number;
  };
  dss_dir: string;
  dss_master_path: string;
  dss_master_preview: string;
  dss_files: string[];
  dss_compile_summary: DssCompileSummary;
  solver_handoff: {
    project_id: string;
    handoff_dir: string;
    dss_dir: string;
    dss_master_path: string;
    status: string;
    notes: string[];
  };
  solver_workspace?: {
    project_id?: string;
    workspace_dir?: string;
    inputs_dir?: string;
    registry_path?: string;
    registry_relative_path?: string;
    strategy_library_path?: string | null;
    strategy_library_relative_path?: string | null;
    tariff_path?: string | null;
    tariff_relative_path?: string | null;
    dss_master_path?: string;
    outputs_dir?: string;
    command_path?: string;
    solver_command?: {
      entry?: string;
      args?: string[];
      registry_path?: string;
      strategy_library_path?: string | null;
      output_dir?: string;
      dss_master_path?: string;
    };
    registry_row_count?: number;
    warnings?: string[];
    errors?: string[];
    ready_for_solver?: boolean;
  };
};

export async function fetchBuildPreview(projectId: string): Promise<BuildPreviewResponse> {
  return http<BuildPreviewResponse>(`/api/build/project/${projectId}/preview`);
}

export async function triggerBuild(projectId: string): Promise<{ success: boolean; project_id: string; manifest_path: string; manifest: BuildManifest }> {
  return http<{ success: boolean; project_id: string; manifest_path: string; manifest: BuildManifest }>(
    `/api/build/project/${projectId}/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    },
  );
}

export async function fetchBuildManifest(projectId: string): Promise<BuildManifest> {
  return http<BuildManifest>(`/api/build/project/${projectId}/manifest`);
}

export async function fetchSearchSpaceInference(projectId: string): Promise<SearchSpaceInferenceResponse> {
  return http<SearchSpaceInferenceResponse>(`/api/build/project/${projectId}/inference-table`);
}

export type GridHealthCheck = {
  name: string;
  status: string;
  detail: string;
};

export type GridHealthRecommendation = {
  type: string;
  node_id?: string;
  message: string;
  rated_kva?: number;
  load_kva?: number;
  loading_pct?: number;
  current_tap?: number;
  recommended_tap?: number;
  total_load_kvar?: number;
  recommended_kvar?: number;
};

export type GridHealthResult = {
  passed: boolean;
  checks: GridHealthCheck[];
  warnings: string[];
  errors: string[];
  recommendations: GridHealthRecommendation[];
  summary: {
    transformer_count: number;
    overloaded_transformer_count: number;
    total_load_kw: number;
    total_load_kvar: number;
  };
};

export type GridHealthResponse = {
  success: boolean;
  project_id: string;
  grid_health: GridHealthResult;
};

export async function fetchGridHealth(projectId: string): Promise<GridHealthResponse> {
  return http<GridHealthResponse>(`/api/build/project/${projectId}/grid-health`);
}
