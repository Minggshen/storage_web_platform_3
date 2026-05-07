
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    GRID = "grid"
    SOURCE = "source"
    TRANSFORMER = "transformer"
    DISTRIBUTION_TRANSFORMER = "distribution_transformer"
    BUS = "bus"
    LOAD = "load"
    STORAGE = "storage"
    STORAGE_ACCESS = "storage_access"
    RING_MAIN_UNIT = "ring_main_unit"
    BRANCH = "branch"
    SWITCH = "switch"
    BREAKER = "breaker"
    FUSE = "fuse"
    REGULATOR = "regulator"
    CAPACITOR = "capacitor"
    PV = "pv"
    WIND = "wind"


class EdgeType(str, Enum):
    LINE = "line"
    NORMAL_LINE = "normal_line"
    SPECIAL_LINE = "special_line"
    FEEDER = "feeder"


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


class ProjectPosition(BaseModel):
    x: float = 0.0
    y: float = 0.0


class RuntimeBinding(BaseModel):
    year_map_file_id: Optional[str] = None
    model_library_file_id: Optional[str] = None
    year_map_file_name: Optional[str] = None
    model_library_file_name: Optional[str] = None


class AssetRef(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    source_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NetworkNode(BaseModel):
    id: str
    type: NodeType
    name: str
    position: ProjectPosition = Field(default_factory=ProjectPosition)
    params: Dict[str, Any] = Field(default_factory=dict)
    runtime_binding: Optional[RuntimeBinding] = None
    tags: List[str] = Field(default_factory=list)


class NetworkEdge(BaseModel):
    id: str
    type: EdgeType = EdgeType.LINE
    name: Optional[str] = None
    from_node_id: str
    to_node_id: str
    params: Dict[str, Any] = Field(default_factory=dict)


class NetworkModel(BaseModel):
    nodes: List[NetworkNode] = Field(default_factory=list)
    edges: List[NetworkEdge] = Field(default_factory=list)
    economic_parameters: Dict[str, Any] = Field(default_factory=dict)


class TariffConfig(BaseModel):
    asset: Optional[AssetRef] = None
    tariff_year: Optional[int] = None


class DeviceRecord(BaseModel):
    # core fields used by the backend and later Python optimization
    enabled: bool = True
    vendor: str
    model: str
    series_name: Optional[str] = None
    device_family: Optional[str] = None
    system_topology_type: Optional[str] = None
    application_scene: Optional[str] = None
    cni_fit_level: Optional[str] = None
    is_default_candidate: Optional[bool] = None

    ems_package: Optional[str] = None
    ems_package_name: Optional[str] = None
    has_builtin_ems: Optional[bool] = None
    requires_external_pcs: Optional[bool] = None
    supports_black_start: Optional[bool] = None
    supports_offgrid_microgrid: Optional[bool] = None

    battery_chemistry: Optional[str] = None
    rated_power_kw: Optional[float] = None
    rated_energy_kwh: Optional[float] = None
    usable_energy_kwh_at_fat: Optional[float] = None
    duration_hour: Optional[float] = None
    dc_voltage_range_v: Optional[str] = None
    ac_grid_voltage_v: Optional[str] = None
    battery_config: Optional[str] = None

    cooling_type: Optional[str] = None
    fire_detection: Optional[str] = None
    fire_suppression: Optional[str] = None
    backup_system: Optional[str] = None
    accident_ventilation: Optional[bool] = None
    pack_level_firefighting_optional: Optional[bool] = None
    explosion_relief_optional: Optional[bool] = None
    msd_required: Optional[bool] = None
    communication_protocol: Optional[str] = None

    # manual safety / operating limits
    safety_level: Optional[str] = None
    manual_safety_grade: Optional[str] = None
    manual_safety_notes: Optional[str] = None
    cycle_life: Optional[int] = None
    soc_min: Optional[float] = None
    soc_max: Optional[float] = None
    efficiency_pct: Optional[float] = None

    ip_system: Optional[str] = None
    corrosion_grade: Optional[str] = None
    install_mode: Optional[str] = None
    aux_power_interface: Optional[str] = None
    dimension_w_mm: Optional[float] = None
    dimension_d_mm: Optional[float] = None
    dimension_h_mm: Optional[float] = None
    weight_kg: Optional[float] = None

    # economics
    price_yuan_per_wh: Optional[float] = None
    energy_unit_price_yuan_per_kwh: Optional[float] = None
    power_related_capex_yuan_per_kw: Optional[float] = None
    station_integration_capex_ratio: Optional[float] = None
    fire_protection_capex_ratio: Optional[float] = None
    annual_insurance_rate_on_capex: Optional[float] = None
    annual_safety_maintenance_rate_on_capex: Optional[float] = None
    annual_fire_system_inspection_rate_on_capex: Optional[float] = None
    price_status: Optional[str] = None
    quote_source: Optional[str] = None
    source_files: Optional[str] = None

    extra: Dict[str, Any] = Field(default_factory=dict)


class DeviceLibraryConfig(BaseModel):
    asset: Optional[AssetRef] = None
    records: List[DeviceRecord] = Field(default_factory=list)


class CalculationMode(str, Enum):
    ECONOMIC = "economic"
    SAFETY = "safety"
    BALANCED = "balanced"


class SolveConfig(BaseModel):
    mode: CalculationMode = CalculationMode.ECONOMIC
    dispatch_mode: Literal["day_ahead", "fixed"] = "day_ahead"
    run_mode: Literal["snapshot", "annual"] = "annual"
    allow_high_c_rate: bool = False
    strict_transformer_reserve: bool = True
    output_plots: bool = True
    extra: Dict[str, Any] = Field(default_factory=dict)


class SolverExecutionMode(str, Enum):
    STAGED_WORKSPACE = "staged_workspace"
    DIRECT_COMMAND = "direct_command"


class SolverBindingConfig(BaseModel):
    enabled: bool = False
    python_executable: Optional[str] = None
    solver_project_root: Optional[str] = None
    solver_entry_relative: Optional[str] = None
    solver_working_dir: Optional[str] = None
    execution_mode: SolverExecutionMode = SolverExecutionMode.STAGED_WORKSPACE
    command_template: Optional[str] = None
    default_cli_args: List[str] = Field(default_factory=list)
    environment: Dict[str, str] = Field(default_factory=dict)
    exclude_dirs: List[str] = Field(
        default_factory=lambda: [".git", ".venv", "venv", "__pycache__", "outputs", "build", ".idea", ".vscode", "node_modules"]
    )
    ignore_globs: List[str] = Field(default_factory=lambda: ["*.pyc", "*.pyo", "*.log", "*.tmp"])
    notes: Optional[str] = None


class ProjectModel(BaseModel):
    project_id: Optional[str] = None
    project_name: str
    version: str = "2.1.0"
    created_at: Optional[str] = None
    description: Optional[str] = None
    network: NetworkModel = Field(default_factory=NetworkModel)
    tariff: TariffConfig = Field(default_factory=TariffConfig)
    device_library: DeviceLibraryConfig = Field(default_factory=DeviceLibraryConfig)
    solve_config: SolveConfig = Field(default_factory=SolveConfig)
    solver_binding: SolverBindingConfig = Field(default_factory=SolverBindingConfig)
    assets: Dict[str, AssetRef] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationItem(BaseModel):
    group_key: str
    group_label: str
    rule_key: str
    title: str
    status: ValidationStatus
    message: str
    location: Optional[str] = None
    detail: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class ValidationGroup(BaseModel):
    group_key: str
    group_label: str
    pass_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    items: List[ValidationItem] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    pass_count: int = 0
    warning_count: int = 0
    error_count: int = 0


class ProjectValidationReport(BaseModel):
    ok: bool
    summary: ValidationSummary
    groups: List[ValidationGroup]


class SaveProjectRequest(BaseModel):
    project: ProjectModel


class SaveProjectResponse(BaseModel):
    success: bool
    project_id: str
    project_file_path: str


class LoadProjectResponse(BaseModel):
    success: bool
    project: ProjectModel


class ListProjectsItem(BaseModel):
    project_id: str
    project_name: str
    created_at: str
    project_file_path: str


class ListProjectsResponse(BaseModel):
    success: bool
    projects: List[ListProjectsItem]


class ValidateProjectRequest(BaseModel):
    project: ProjectModel


class ValidateProjectResponse(BaseModel):
    success: bool
    report: ProjectValidationReport


class CreateEmptyProjectRequest(BaseModel):
    project_name: str
    description: Optional[str] = None


class CreateEmptyProjectResponse(BaseModel):
    success: bool
    project: ProjectModel
    project_file_path: str


class UpsertNodeRequest(BaseModel):
    project_id: str
    node: NetworkNode


class UpsertNodeResponse(BaseModel):
    success: bool
    project: ProjectModel
    project_file_path: str


class DeleteNodeRequest(BaseModel):
    project_id: str
    node_id: str


class DeleteNodeResponse(BaseModel):
    success: bool
    project: ProjectModel
    deleted_node_id: str
    deleted_edge_ids: List[str] = Field(default_factory=list)
    project_file_path: str


class UpsertEdgeRequest(BaseModel):
    project_id: str
    edge: NetworkEdge


class UpsertEdgeResponse(BaseModel):
    success: bool
    project: ProjectModel
    project_file_path: str


class DeleteEdgeRequest(BaseModel):
    project_id: str
    edge_id: str


class DeleteEdgeResponse(BaseModel):
    success: bool
    project: ProjectModel
    deleted_edge_id: str
    project_file_path: str


class TopologyCatalogItem(BaseModel):
    type: str
    label: str
    required_params: List[str] = Field(default_factory=list)
    recommended_params: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TopologyCatalogResponse(BaseModel):
    success: bool
    node_catalog: List[TopologyCatalogItem]
    edge_catalog: List[TopologyCatalogItem]


class AssetValidationMessage(BaseModel):
    status: ValidationStatus
    title: str
    message: str
    detail: Optional[str] = None


class AssetValidationReport(BaseModel):
    ok: bool
    asset_kind: str
    pass_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    messages: List[AssetValidationMessage] = Field(default_factory=list)
    parsed_preview: Dict[str, Any] = Field(default_factory=dict)


class ProjectAssetsResponse(BaseModel):
    success: bool
    project_id: str
    assets: List[AssetRef]


class RuntimeBindingRequest(BaseModel):
    project_id: str
    node_id: str
    year_map_file_id: str
    model_library_file_id: str


class RuntimeBindingResponse(BaseModel):
    success: bool
    project: ProjectModel
    node_id: str
    year_map_asset: AssetRef
    model_library_asset: AssetRef
    year_map_report: AssetValidationReport
    model_library_report: AssetValidationReport
    project_file_path: str


class TariffBindingRequest(BaseModel):
    project_id: str
    file_id: str
    tariff_year: Optional[int] = None


class TariffBindingResponse(BaseModel):
    success: bool
    project: ProjectModel
    asset: AssetRef
    report: AssetValidationReport
    project_file_path: str


class DeviceLibraryUploadResponse(BaseModel):
    success: bool
    project: ProjectModel
    asset: AssetRef
    report: AssetValidationReport
    imported_record_count: int
    project_file_path: str


class TariffUploadResponse(BaseModel):
    success: bool
    project: ProjectModel
    asset: AssetRef
    report: AssetValidationReport
    project_file_path: str


class RuntimeUploadResponse(BaseModel):
    success: bool
    project: ProjectModel
    node_id: str
    year_map_asset: AssetRef
    model_library_asset: AssetRef
    year_map_report: AssetValidationReport
    model_library_report: AssetValidationReport
    project_file_path: str


class UpsertDeviceRecordRequest(BaseModel):
    project_id: str
    record: DeviceRecord


class UpsertDeviceRecordResponse(BaseModel):
    success: bool
    project: ProjectModel
    record: DeviceRecord
    project_file_path: str


class DeleteDeviceRecordRequest(BaseModel):
    project_id: str
    vendor: str
    model: str


class DeleteDeviceRecordResponse(BaseModel):
    success: bool
    project: ProjectModel
    deleted_vendor: str
    deleted_model: str
    project_file_path: str


class ConfigureSolverRequest(BaseModel):
    project_id: str
    solver_binding: SolverBindingConfig


class ConfigureSolverResponse(BaseModel):
    success: bool
    project: ProjectModel
    project_file_path: str


class SolverTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SolverRunRequest(BaseModel):
    auto_build: bool = True
    clean_build_dir: bool = True
    package_zip: bool = True
    export_registry_xlsx: bool = True
    clean_solver_workspace: bool = True
    task_name: Optional[str] = None
    command_template: Optional[str] = None
    default_cli_args: List[str] = Field(default_factory=list)
    environment: Dict[str, str] = Field(default_factory=dict)
    disable_plots: bool = True
    output_subdir_name: str = "integrated_optimization"


class SolverTaskInfo(BaseModel):
    task_id: str
    project_id: str
    task_name: Optional[str] = None
    status: SolverTaskStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    solver_project_root: Optional[str] = None
    solver_entry_relative: Optional[str] = None
    execution_mode: SolverExecutionMode = SolverExecutionMode.STAGED_WORKSPACE
    run_root: Optional[str] = None
    staged_solver_root: Optional[str] = None
    outputs_dir: Optional[str] = None
    stdout_log: Optional[str] = None
    stderr_log: Optional[str] = None
    command: List[str] = Field(default_factory=list)
    return_code: Optional[int] = None
    error_message: Optional[str] = None
    build_summary_path: Optional[str] = None
    result_files: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SolverRunResponse(BaseModel):
    success: bool
    task: SolverTaskInfo


class SolverTaskResponse(BaseModel):
    success: bool
    task: SolverTaskInfo


class SolverResultsResponse(BaseModel):
    success: bool
    task: SolverTaskInfo
    result_files: List[Dict[str, Any]] = Field(default_factory=list)


class SolverSummaryResponse(BaseModel):
    success: bool
    task: SolverTaskInfo
    summary_rows: List[Dict[str, Any]] = Field(default_factory=list)
    summary_json_path: Optional[str] = None
    summary_csv_path: Optional[str] = None


# ===== Workflow-page support models =====

class ProjectDashboardStepStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepCard(BaseModel):
    key: str
    label: str
    status: ProjectDashboardStepStatus
    detail: Optional[str] = None
    route: Optional[str] = None
    counts: Dict[str, Any] = Field(default_factory=dict)


class ProjectDashboardData(BaseModel):
    project_id: str
    project_name: str
    description: Optional[str] = None
    node_count: int = 0
    edge_count: int = 0
    load_node_count: int = 0
    runtime_bound_load_count: int = 0
    has_tariff: bool = False
    has_device_library: bool = False
    build_ready: bool = False
    build_manifest_exists: bool = False
    latest_solver_status: Optional[str] = None
    latest_summary: Dict[str, Any] = Field(default_factory=dict)
    steps: List[WorkflowStepCard] = Field(default_factory=list)


class ProjectDashboardResponse(BaseModel):
    success: bool
    dashboard: ProjectDashboardData


class CreateProjectRequest(BaseModel):
    project_name: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class CreateProjectResponse(BaseModel):
    success: bool
    project: ProjectModel
    project_file_path: str


class DeleteProjectResponse(BaseModel):
    success: bool
    project_id: str
    deleted_path: str


class CloneProjectRequest(BaseModel):
    new_project_name: Optional[str] = None


class CloneProjectResponse(BaseModel):
    success: bool
    source_project_id: str
    project: ProjectModel
    project_file_path: str


class ReplaceTopologyRequest(BaseModel):
    project_id: str
    network: NetworkModel


class ReplaceTopologyResponse(BaseModel):
    success: bool
    project: ProjectModel
    project_file_path: str


class SearchSpaceInferenceRow(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    transformer_capacity_kva: Optional[float] = None
    transformer_pf_limit: Optional[float] = None
    transformer_reserve_ratio: Optional[float] = None
    grid_interconnection_limit_kw: Optional[float] = None
    peak_kw: Optional[float] = None
    valley_kw: Optional[float] = None
    annual_mean_kw: Optional[float] = None
    mean_daily_energy_kwh: Optional[float] = None
    transformer_limit_kw: Optional[float] = None
    search_power_min_kw: Optional[float] = None
    device_power_max_kw: Optional[float] = None
    search_duration_min_h: Optional[float] = None
    search_duration_max_h: Optional[float] = None
    inference_source: Optional[str] = None
    basis: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    explain: List[Dict[str, Any]] = Field(default_factory=list)


class SearchSpaceInferenceResponse(BaseModel):
    success: bool
    project_id: str
    rows: List[SearchSpaceInferenceRow] = Field(default_factory=list)


class SolverTaskLogsResponse(BaseModel):
    success: bool
    task: SolverTaskInfo
    stdout_text: str = ""
    stderr_text: str = ""
