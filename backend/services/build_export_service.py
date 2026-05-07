from __future__ import annotations

import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from services.dss_builder_service import DssBuilderService
from services.search_space_inference_service import SearchSpaceInferenceService


class BuildExportService:
    """
    Build/export service used by the frontend workspace.

    Responsibilities:
    - validate whether the visual topology is buildable
    - emit build manifest
    - compile OpenDSS inputs under build/inputs/dss/visual_model
    - prepare a lightweight solver handoff view
    """

    def __init__(
        self,
        project_service: Any = None,
        validation_service: Any = None,
        data_root: str | Path | None = None,
    ) -> None:
        # compatibility with older positional misuse: BuildExportService(project_service)
        if project_service is not None and not hasattr(project_service, "load_project") and data_root is None:
            if isinstance(project_service, (str, Path)):
                data_root = project_service
                project_service = None

        backend_root = Path(__file__).resolve().parent.parent
        self.project_service = project_service
        self.validation_service = validation_service
        self.data_root = Path(data_root) if data_root is not None else backend_root / "data" / "projects"
        self.dss_builder = DssBuilderService()
        self.search_space_inference = SearchSpaceInferenceService()

    def get_build_preview(self, project_id: str) -> dict[str, Any]:
        return self.preview_build(project_id)

    def preview_build(self, project_id: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        topology = self._extract_topology(project)
        validation = self._validate_topology(topology)
        warnings = validation["warnings"]
        errors = validation["errors"]
        summary = {
            "project_id": project_id,
            "project_name": str(project.get("project_name") or project.get("name") or project_id),
            "ready_for_build": validation["ready_for_build"],
            "warnings": warnings,
            "errors": errors,
            "node_count": len(topology["nodes"]),
            "edge_count": len(topology["edges"]),
            "grid_count": validation["grid_count"],
            "transformer_count": validation["transformer_count"],
            "load_count": validation["load_count"],
            "active_edge_count": validation["active_edge_count"],
            "disconnected_count": validation["disconnected_count"],
        }
        return {
            "success": True,
            "summary": summary,
            "validation": validation,
            "preview": {
                "nodes": topology["nodes"],
                "edges": topology["edges"],
                "economic_parameters": topology.get("economic_parameters", {}),
            },
        }

    def build_project(self, project_id: str) -> dict[str, Any]:
        return self.generate_build(project_id)

    def generate_build(self, project_id: str) -> dict[str, Any]:
        project = self._load_project(project_id)
        topology = self._extract_topology(project)

        project_dir = self._project_dir(project_id)
        build_dir = project_dir / "build"
        inputs_dir = build_dir / "inputs"
        dss_dir = inputs_dir / "dss" / "visual_model"
        manifest_dir = build_dir / "manifest"

        dss_dir.mkdir(parents=True, exist_ok=True)
        manifest_dir.mkdir(parents=True, exist_ok=True)

        preview = self.preview_build(project_id)
        dss_payload = self.dss_builder.compile_topology(project_id, topology, dss_dir)

        handoff = self._prepare_solver_handoff(project_id, build_dir, inputs_dir, dss_payload)
        solver_workspace = self._prepare_solver_workspace(project_id, project, build_dir, dss_payload)

        manifest = {
            "success": True,
            "project_id": project_id,
            "project_name": str(project.get("project_name") or project.get("name") or project_id),
            "build_dir": str(build_dir),
            "inputs_dir": str(inputs_dir),
            "ready_for_build": preview["summary"]["ready_for_build"],
            "warnings": preview["summary"]["warnings"],
            "errors": preview["summary"]["errors"],
            "topology_summary": {
                "node_count": len(topology["nodes"]),
                "edge_count": len(topology["edges"]),
            },
            **dss_payload,
            "solver_handoff": handoff,
            "solver_workspace": solver_workspace,
        }

        manifest_path = manifest_dir / "build_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "success": True,
            "project_id": project_id,
            "manifest_path": str(manifest_path),
            "manifest": manifest,
        }

    def generate_project_build(self, project_id: str) -> dict[str, Any]:
        return self.generate_build(project_id)

    def get_build_manifest(self, project_id: str) -> dict[str, Any]:
        return self.read_build_manifest(project_id)

    def read_build_manifest(self, project_id: str) -> dict[str, Any]:
        manifest_path = self._project_dir(project_id) / "build" / "manifest" / "build_manifest.json"
        if not manifest_path.exists():
            generated = self.generate_build(project_id)
            return generated["manifest"]
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def _prepare_solver_handoff(
        self,
        project_id: str,
        build_dir: Path,
        inputs_dir: Path,
        dss_payload: dict[str, Any],
    ) -> dict[str, Any]:
        handoff_dir = build_dir / "solver_handoff"
        handoff_dir.mkdir(parents=True, exist_ok=True)

        target_dss_dir = handoff_dir / "dss"
        if target_dss_dir.exists():
            shutil.rmtree(target_dss_dir)
        shutil.copytree(Path(dss_payload["dss_dir"]), target_dss_dir)

        summary = {
            "project_id": project_id,
            "handoff_dir": str(handoff_dir),
            "dss_dir": str(target_dss_dir),
            "dss_master_path": str(target_dss_dir / "Master.dss"),
            "status": "ready",
            "notes": [
                "该目录用于 solver 阶段读取可视化拓扑编译后的 OpenDSS 输入。",
                "当前版本仅做输入交接，不强制改写现有求解器主流程。",
            ],
        }
        (handoff_dir / "handoff_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    def _prepare_solver_workspace(
        self,
        project_id: str,
        project: dict[str, Any],
        build_dir: Path,
        dss_payload: dict[str, Any],
    ) -> dict[str, Any]:
        workspace_dir = build_dir / "solver_workspace"
        inputs_dir = workspace_dir / "inputs"
        registry_dir = inputs_dir / "registry"
        node_loads_dir = inputs_dir / "node_loads"
        storage_dir = inputs_dir / "storage"
        tariff_dir = inputs_dir / "tariff"
        dss_dir = inputs_dir / "dss" / "visual_model"
        outputs_dir = workspace_dir / "outputs" / "integrated_optimization"

        for path in [registry_dir, node_loads_dir, storage_dir, tariff_dir, dss_dir.parent, outputs_dir]:
            path.mkdir(parents=True, exist_ok=True)

        if dss_dir.exists():
            shutil.rmtree(dss_dir)
        shutil.copytree(Path(dss_payload["dss_dir"]), dss_dir)

        warnings: list[str] = []
        errors: list[str] = []

        tariff_rel_path, tariff_abs_path = self._prepare_tariff_input(project, tariff_dir, errors)
        strategy_rel_path, strategy_abs_path = self._prepare_strategy_library(project, storage_dir, errors, warnings)
        registry_rows = self._build_registry_rows(
            project=project,
            node_loads_dir=node_loads_dir,
            workspace_dir=workspace_dir,
            tariff_rel_path=tariff_rel_path,
            errors=errors,
            warnings=warnings,
        )
        runtime_manifest_rel_path = self._write_network_runtime_manifest(
            registry_dir=registry_dir,
            rows=registry_rows,
        )
        if runtime_manifest_rel_path:
            for row in registry_rows:
                row["network_runtime_manifest_path"] = runtime_manifest_rel_path

        selected_target_id = self._resolve_default_storage_target(registry_rows, errors, warnings)

        registry_path = registry_dir / "node_registry.xlsx"
        self._write_registry_xlsx(registry_path, registry_rows)

        command = self._build_solver_command(
            registry_path=registry_path,
            strategy_path=strategy_abs_path,
            output_dir=outputs_dir,
            dss_master_path=dss_dir / "Master.dss",
            project=project,
            selected_target_id=selected_target_id,
        )

        command_path = workspace_dir / "solver_command.json"
        command_path.write_text(json.dumps(command, ensure_ascii=False, indent=2), encoding="utf-8")

        summary = {
            "project_id": project_id,
            "workspace_dir": str(workspace_dir.resolve()),
            "inputs_dir": str(inputs_dir.resolve()),
            "registry_path": str(registry_path.resolve()),
            "registry_relative_path": "inputs/registry/node_registry.xlsx",
            "strategy_library_path": str(strategy_abs_path.resolve()) if strategy_abs_path else None,
            "strategy_library_relative_path": strategy_rel_path,
            "tariff_path": str(tariff_abs_path.resolve()) if tariff_abs_path else None,
            "tariff_relative_path": tariff_rel_path,
            "dss_master_path": str((dss_dir / "Master.dss").resolve()),
            "network_runtime_manifest_path": str((registry_dir / "network_runtime_manifest.json").resolve()) if runtime_manifest_rel_path else None,
            "network_runtime_manifest_relative_path": runtime_manifest_rel_path,
            "selected_target_id": selected_target_id,
            "outputs_dir": str(outputs_dir.resolve()),
            "command_path": str(command_path.resolve()),
            "solver_command": command,
            "registry_row_count": len(registry_rows),
            "warnings": warnings,
            "errors": errors,
            "ready_for_solver": len(errors) == 0 and len(registry_rows) > 0,
        }
        (workspace_dir / "workspace_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    def _prepare_tariff_input(
        self,
        project: dict[str, Any],
        tariff_dir: Path,
        errors: list[str],
    ) -> tuple[str | None, Path | None]:
        asset = (project.get("tariff") or {}).get("asset") if isinstance(project.get("tariff"), dict) else None
        source_path = self._asset_path(asset)
        if source_path is None:
            errors.append("未绑定电价表，无法生成求解器 tariff 输入。")
            return None, None

        suffix = source_path.suffix.lower() or ".xlsx"
        target_name = "tariff_annual.csv" if suffix == ".csv" else "tariff_annual.xlsx"
        target_path = tariff_dir / target_name
        shutil.copy2(source_path, target_path)
        return f"inputs/tariff/{target_name}", target_path

    def _prepare_strategy_library(
        self,
        project: dict[str, Any],
        storage_dir: Path,
        errors: list[str],
        warnings: list[str],
    ) -> tuple[str | None, Path | None]:
        target_path = storage_dir / "工商业储能设备策略库.xlsx"
        records = ((project.get("device_library") or {}).get("records") or []) if isinstance(project.get("device_library"), dict) else []
        if records:
            self._write_strategy_library_xlsx(target_path, records)
            return "inputs/storage/工商业储能设备策略库.xlsx", target_path

        asset = (project.get("device_library") or {}).get("asset") if isinstance(project.get("device_library"), dict) else None
        source_path = self._asset_path(asset)
        if source_path is None:
            errors.append("未绑定设备策略库，无法生成求解器 strategy-library 输入。")
            return None, None

        if source_path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
            errors.append("设备策略库不是 Excel 文件，且项目中没有可导出的设备记录。")
            return None, None

        shutil.copy2(source_path, target_path)
        warnings.append("设备策略库按原文件复制，需确认其 sheet/schema 与求解器兼容。")
        return "inputs/storage/工商业储能设备策略库.xlsx", target_path

    def _load_runtime_stats(self, year_path: Path, model_path: Path) -> dict[str, Any]:
        if not year_path.exists() or not model_path.exists():
            return {}

        weights: dict[str, int] = {}
        try:
            with year_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    model_id = str(row.get("internal_model_id") or "").strip()
                    if model_id:
                        weights[model_id] = weights.get(model_id, 0) + 1
        except Exception:
            return {}

        peak_kw = None
        valley_kw = None
        weighted_mean = 0.0
        total_days = 0
        daily_energy_acc = 0.0
        try:
            with model_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    model_id = str(row.get("internal_model_id") or "").strip()
                    w = weights.get(model_id, 0)
                    if w <= 0:
                        continue
                    vals = []
                    for i in range(24):
                        for key in (f"h{i:02d}", f"H{i:02d}", f"load_{i:02d}", f"p_{i:02d}"):
                            if key in row:
                                try:
                                    vals.append(float(row[key]))
                                except Exception:
                                    vals.append(0.0)
                                break
                    if not vals:
                        continue
                    local_peak = max(vals)
                    local_valley = min(vals)
                    local_mean = sum(vals) / len(vals)
                    local_daily_energy = sum(vals)
                    peak_kw = local_peak if peak_kw is None else max(peak_kw, local_peak)
                    valley_kw = local_valley if valley_kw is None else min(valley_kw, local_valley)
                    weighted_mean += local_mean * w
                    daily_energy_acc += local_daily_energy * w
                    total_days += w
        except Exception:
            return {}

        return {
            "peak_kw": peak_kw,
            "valley_kw": valley_kw,
            "annual_mean_kw": (weighted_mean / total_days) if total_days else None,
            "mean_daily_energy_kwh": (daily_energy_acc / total_days) if total_days else None,
        }

    def _build_registry_rows(
        self,
        project: dict[str, Any],
        node_loads_dir: Path,
        workspace_dir: Path,
        tariff_rel_path: str | None,
        errors: list[str],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        network = project.get("network") if isinstance(project.get("network"), dict) else {}
        nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
        economic_params = network.get("economic_parameters") if isinstance(network.get("economic_parameters"), dict) else {}
        assets = project.get("assets") if isinstance(project.get("assets"), dict) else {}
        device_records = ((project.get("device_library") or {}).get("records") or []) if isinstance(project.get("device_library"), dict) else []

        load_index = 0
        for node in nodes:
            if str(node.get("type")) != "load":
                continue
            load_index += 1
            params = node.get("params") if isinstance(node.get("params"), dict) else {}
            node_id = self._safe_int(params.get("node_id"), load_index)
            category = str(params.get("category") or "industrial").strip() or "industrial"
            internal_id = self._safe_name(str(node.get("id") or f"load_{load_index:03d}"))
            dss_bus_name = self._dss_bus_name(node, node_id)
            dss_load_name = self._dss_load_name(node, node_id)
            dss_phases = 3
            allow_grid_export = params.get(
                "allow_grid_export",
                params.get("allow_reverse_power_to_grid", params.get("allow_export_to_grid", False)),
            )
            node_dir_rel = f"inputs/node_loads/{category}/{internal_id}"
            node_dir = workspace_dir / node_dir_rel
            node_dir.mkdir(parents=True, exist_ok=True)

            binding = node.get("runtime_binding") if isinstance(node.get("runtime_binding"), dict) else {}
            year_asset = assets.get(str(binding.get("year_map_file_id") or ""))
            model_asset = assets.get(str(binding.get("model_library_file_id") or ""))

            year_path = self._asset_path(year_asset)
            model_path = self._asset_path(model_asset)
            if year_path is None or model_path is None:
                errors.append(f"负荷节点 {node.get('name') or node.get('id')} 未完整绑定 runtime_year_model_map/runtime_model_library。")
                continue

            shutil.copy2(year_path, node_dir / "runtime_year_model_map.csv")
            shutil.copy2(model_path, node_dir / "runtime_model_library.csv")

            transformer_capacity_kva = self._safe_float(params.get("transformer_capacity_kva"), 0.0) or None
            transformer_pf_limit = self._safe_float(params.get("transformer_pf_limit"), self._safe_float(params.get("pf"), 0.95))
            transformer_reserve_ratio = self._safe_float(params.get("transformer_reserve_ratio"), 0.15)
            grid_interconnection_limit_kw = None
            inference = self.search_space_inference.infer(
                node_params=params,
                runtime_stats=self._load_runtime_stats(year_path, model_path),
                device_records=device_records,
                transformer_capacity_kva=transformer_capacity_kva,
                transformer_pf_limit=transformer_pf_limit,
                transformer_reserve_ratio=transformer_reserve_ratio,
                grid_interconnection_limit_kw=grid_interconnection_limit_kw,
            )

            rows.append(
                {
                    "internal_model_id": internal_id,
                    "enabled": 1 if self._safe_bool(params.get("enabled"), True) else 0,
                    "optimize_storage": 1 if self._safe_bool(params.get("optimize_storage"), False) else 0,
                    "allow_grid_export": 1 if self._safe_bool(allow_grid_export, False) else 0,
                    "node_id": node_id,
                    "scenario_name": str(node.get("name") or internal_id),
                    "category": category,
                    "node_dir": node_dir_rel,
                    "year_model_map_file": "runtime_year_model_map.csv",
                    "model_library_file": "runtime_model_library.csv",
                    "tariff_path": tariff_rel_path or "",
                    "service_calendar_path": "",
                    "pv_capacity_kw": 0.0,
                    "q_to_p_ratio": self._safe_float(params.get("q_to_p_ratio"), 0.25),
                    "description": "",
                    "remarks": str(params.get("remarks") or params.get("description") or ""),
                    "target_bus_name": dss_bus_name,
                    "target_load_name": dss_load_name,
                    "target_kv_ln": self._normalize_distribution_base_kv(params.get("target_kv_ln")),
                    "static_load_reference_kw": self._safe_float(params.get("design_kw"), 0.0),
                    "dss_bus_name": dss_bus_name,
                    "dss_load_name": dss_load_name,
                    "dss_phases": dss_phases,
                    "transformer_capacity_kva": transformer_capacity_kva,
                    "transformer_pf_limit": transformer_pf_limit,
                    "transformer_reserve_ratio": transformer_reserve_ratio,
                    "grid_interconnection_limit_kw": grid_interconnection_limit_kw,
                    "device_power_max_kw": inference.device_power_max_kw,
                    "search_power_min_kw": inference.search_power_min_kw,
                    "search_duration_min_h": inference.search_duration_min_h,
                    "search_duration_max_h": inference.search_duration_max_h,
                    "include_aux_service_revenue": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_aux_service_revenue", False), False) else 0,
                    "include_capacity_revenue": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_capacity_revenue", False), False) else 0,
                    "include_loss_reduction_revenue": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_loss_reduction_revenue", False), False) else 0,
                    "include_degradation_cost": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_degradation_cost", True), True) else 0,
                    "include_government_subsidy": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_government_subsidy", False), False) else 0,
                    "include_replacement_cost": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_replacement_cost", True), True) else 0,
                    "include_demand_saving": 1 if self._safe_bool(self._economic_param(params, economic_params, "include_demand_saving", True), True) else 0,
                    "default_capacity_price_yuan_per_kw": self._safe_float(self._economic_param(params, economic_params, "default_capacity_price_yuan_per_kw", 0.05), 0.05),
                    "default_delivery_price_yuan_per_kwh": self._safe_float(self._economic_param(params, economic_params, "default_delivery_price_yuan_per_kwh", 0.10), 0.10),
                    "default_penalty_price_yuan_per_kwh": self._safe_float(self._economic_param(params, economic_params, "default_penalty_price_yuan_per_kwh", 0.20), 0.20),
                    "default_activation_factor": self._safe_float(self._economic_param(params, economic_params, "default_activation_factor", 0.15), 0.15),
                    "max_service_power_ratio": self._safe_float(self._economic_param(params, economic_params, "max_service_power_ratio", 0.30), 0.30),
                    "capacity_service_price_yuan_per_kw_day": self._safe_float(self._economic_param(params, economic_params, "capacity_service_price_yuan_per_kw_day", 0.0), 0.0),
                    "capacity_revenue_eligible_days": self._safe_float(self._economic_param(params, economic_params, "capacity_revenue_eligible_days", 365.0), 365.0),
                    "network_loss_price_yuan_per_kwh": self._safe_float(self._economic_param(params, economic_params, "network_loss_price_yuan_per_kwh", 0.30), 0.30),
                    "network_loss_proxy_rate": self._safe_float(self._economic_param(params, economic_params, "network_loss_proxy_rate", 0.02), 0.02),
                    "government_subsidy_rate_on_capex": self._safe_float(self._economic_param(params, economic_params, "government_subsidy_rate_on_capex", 0.0), 0.0),
                    "government_subsidy_yuan_per_kwh": self._safe_float(self._economic_param(params, economic_params, "government_subsidy_yuan_per_kwh", 0.0), 0.0),
                    "government_subsidy_yuan_per_kw": self._safe_float(self._economic_param(params, economic_params, "government_subsidy_yuan_per_kw", 0.0), 0.0),
                    "government_subsidy_cap_yuan": self._safe_float(self._economic_param(params, economic_params, "government_subsidy_cap_yuan", 0.0), 0.0),
                    "replacement_cost_ratio": self._safe_float(self._economic_param(params, economic_params, "replacement_cost_ratio", 0.60), 0.60),
                    "replacement_year_override": self._safe_float(self._economic_param(params, economic_params, "replacement_year_override", 0.0), 0.0),
                    "replacement_trigger_soh": self._safe_float(self._economic_param(params, economic_params, "replacement_trigger_soh", 0.70), 0.70),
                    "replacement_reset_soh": self._safe_float(self._economic_param(params, economic_params, "replacement_reset_soh", 0.95), 0.95),
                    "annual_fixed_om_yuan_per_kw_year": self._safe_float(self._economic_param(params, economic_params, "annual_fixed_om_yuan_per_kw_year", 18.0), 18.0),
                    "annual_variable_om_yuan_per_kwh": self._safe_float(self._economic_param(params, economic_params, "annual_variable_om_yuan_per_kwh", 0.004), 0.004),
                    "project_life_years": self._safe_int(self._economic_param(params, economic_params, "project_life_years", 20), 20),
                    "discount_rate": self._safe_float(self._economic_param(params, economic_params, "discount_rate", 0.06), 0.06),
                    "annual_revenue_growth_rate": self._safe_float(self._economic_param(params, economic_params, "annual_revenue_growth_rate", 0.0), 0.0),
                    "annual_om_growth_rate": self._safe_float(self._economic_param(params, economic_params, "annual_om_growth_rate", 0.02), 0.02),
                    "power_related_capex_yuan_per_kw": self._safe_float(self._economic_param(params, economic_params, "power_related_capex_yuan_per_kw", 300.0), 300.0),
                    "integration_markup_ratio": self._safe_float(self._economic_param(params, economic_params, "integration_markup_ratio", 0.15), 0.15),
                    "safety_markup_ratio": self._safe_float(self._economic_param(params, economic_params, "safety_markup_ratio", 0.02), 0.02),
                    "other_capex_yuan": self._safe_float(self._economic_param(params, economic_params, "other_capex_yuan", 0.0), 0.0),
                    "degradation_cost_yuan_per_kwh_throughput": self._safe_float(self._economic_param(params, economic_params, "degradation_cost_yuan_per_kwh_throughput", 0.03), 0.03),
                    "battery_capex_share": self._safe_float(self._economic_param(params, economic_params, "battery_capex_share", 0.60), 0.60),
                    "cycle_life_efc": self._safe_float(self._economic_param(params, economic_params, "cycle_life_efc", 8000.0), 8000.0),
                    "annual_cycle_limit": self._safe_float(self._economic_param(params, economic_params, "annual_cycle_limit", 0.0), 0.0),
                    "calendar_life_years": self._safe_float(self._economic_param(params, economic_params, "calendar_life_years", 20.0), 20.0),
                    "calendar_fade_share": self._safe_float(self._economic_param(params, economic_params, "calendar_fade_share", 0.15), 0.15),
                    "min_degradation_cost_ratio": self._safe_float(self._economic_param(params, economic_params, "min_degradation_cost_ratio", 0.0), 0.0),
                    "dispatch_mode": str(params.get("dispatch_mode") or "hybrid"),
                    "demand_charge_yuan_per_kw_month": self._safe_float(
                        self._economic_param(
                            params,
                            economic_params,
                            "demand_charge_yuan_per_kw_month",
                            self._economic_param(params, economic_params, "daily_demand_shadow_yuan_per_kw", 48.0),
                        ),
                        48.0,
                    ),
                    "daily_demand_shadow_yuan_per_kw": self._safe_float(
                        self._economic_param(
                            params,
                            economic_params,
                            "daily_demand_shadow_yuan_per_kw",
                            self._economic_param(params, economic_params, "demand_charge_yuan_per_kw_month", 48.0),
                        ),
                        48.0,
                    ),
                    "voltage_penalty_coeff_yuan": self._safe_float(self._economic_param(params, economic_params, "voltage_penalty_coeff_yuan", 0.0), 0.0),
                    "run_mode": str(params.get("run_mode") or "single_user"),
                    "model_year": self._safe_int(params.get("model_year"), 2025),
                }
            )

        if not rows and not errors:
            warnings.append("当前拓扑没有完整可运行的负荷节点，solver registry 为空。")
        return rows

    def _write_network_runtime_manifest(
        self,
        registry_dir: Path,
        rows: list[dict[str, Any]],
    ) -> str | None:
        if not rows:
            return None

        rel_path = "inputs/registry/network_runtime_manifest.json"
        manifest = {
            "version": 1,
            "strict_runtime_only": True,
            "runtime_node_count": len(rows),
            "active_node_ids": [int(row["node_id"]) for row in rows if self._safe_bool(row.get("enabled"), True)],
            "loads": [],
        }
        for row in rows:
            manifest["loads"].append(
                {
                    "internal_model_id": row.get("internal_model_id"),
                    "node_id": row.get("node_id"),
                    "scenario_name": row.get("scenario_name"),
                    "category": row.get("category"),
                    "enabled": row.get("enabled"),
                    "optimize_storage": row.get("optimize_storage"),
                    "node_dir": row.get("node_dir"),
                    "year_model_map_file": row.get("year_model_map_file"),
                    "model_library_file": row.get("model_library_file"),
                    "dss_bus_name": row.get("dss_bus_name"),
                    "dss_load_name": row.get("dss_load_name"),
                    "dss_phases": row.get("dss_phases"),
                    "target_kv_ln": row.get("target_kv_ln"),
                    "q_to_p_ratio": row.get("q_to_p_ratio"),
                    "pv_capacity_kw": row.get("pv_capacity_kw"),
                }
            )

        path = registry_dir / "network_runtime_manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return rel_path

    def _resolve_default_storage_target(
        self,
        rows: list[dict[str, Any]],
        errors: list[str],
        warnings: list[str],
    ) -> str | None:
        if not rows:
            return None

        targets = [
            row
            for row in rows
            if self._safe_bool(row.get("enabled"), True) and self._safe_bool(row.get("optimize_storage"), False)
        ]
        if len(targets) == 1:
            return str(targets[0].get("internal_model_id") or "")
        if not targets:
            errors.append("未指定配储目标：请在一个负荷节点上设置 optimize_storage=1，其他负荷保持 optimize_storage=0 作为背景负荷。")
            return None

        target_ids = ", ".join(str(row.get("internal_model_id") or row.get("scenario_name") or "") for row in targets)
        warnings.append(
            "检测到多个候选配储目标；构建仍可用于求解，计算运行时需要从 target_id 下拉列表选择一个。"
            f"候选目标：{target_ids}。"
        )
        return None

    def _write_registry_xlsx(self, path: Path, rows: list[dict[str, Any]]) -> None:
        headers = [
            "internal_model_id", "enabled", "optimize_storage", "allow_grid_export", "node_id", "scenario_name", "category",
            "node_dir", "year_model_map_file", "model_library_file", "network_runtime_manifest_path",
            "tariff_path", "service_calendar_path",
            "pv_capacity_kw", "q_to_p_ratio", "description", "model_year", "remarks",
            "target_bus_name", "target_load_name", "target_kv_ln", "static_load_reference_kw",
            "dss_bus_name", "dss_load_name", "dss_phases",
            "transformer_capacity_kva", "transformer_pf_limit",
            "transformer_reserve_ratio", "grid_interconnection_limit_kw", "device_power_max_kw",
            "search_power_min_kw", "search_duration_min_h", "search_duration_max_h",
            "include_aux_service_revenue", "include_capacity_revenue", "include_loss_reduction_revenue",
            "include_degradation_cost", "include_government_subsidy", "include_replacement_cost",
            "include_demand_saving",
            "default_capacity_price_yuan_per_kw", "default_delivery_price_yuan_per_kwh",
            "default_penalty_price_yuan_per_kwh", "default_activation_factor", "max_service_power_ratio",
            "capacity_service_price_yuan_per_kw_day", "capacity_revenue_eligible_days",
            "network_loss_price_yuan_per_kwh", "network_loss_proxy_rate",
            "government_subsidy_rate_on_capex", "government_subsidy_yuan_per_kwh",
            "government_subsidy_yuan_per_kw", "government_subsidy_cap_yuan",
            "replacement_cost_ratio", "replacement_year_override", "replacement_trigger_soh", "replacement_reset_soh",
            "annual_fixed_om_yuan_per_kw_year", "annual_variable_om_yuan_per_kwh",
            "project_life_years", "discount_rate", "annual_revenue_growth_rate", "annual_om_growth_rate",
            "power_related_capex_yuan_per_kw", "integration_markup_ratio", "safety_markup_ratio", "other_capex_yuan",
            "degradation_cost_yuan_per_kwh_throughput", "battery_capex_share", "cycle_life_efc", "annual_cycle_limit",
            "calendar_life_years", "calendar_fade_share", "min_degradation_cost_ratio",
            "dispatch_mode", "demand_charge_yuan_per_kw_month", "daily_demand_shadow_yuan_per_kw", "voltage_penalty_coeff_yuan",
            "run_mode",
        ]
        wb = Workbook()
        ws = wb.active
        ws.title = "node_registry"
        ws.append(headers)
        for row in rows:
            ws.append([row.get(header) for header in headers])
        wb.save(path)

    def _write_strategy_library_xlsx(self, path: Path, records: list[dict[str, Any]]) -> None:
        wb = Workbook()
        ws = wb.active
        ws.title = "储能策略与设备库"
        headers = [
            "enabled", "manufacturer", "device_model", "rated_power_kw", "rated_energy_kwh",
            "duration_hour", "battery_chemistry", "manual_safety_grade", "round_trip_efficiency",
            "energy_unit_price_yuan_per_kwh", "power_related_capex_yuan_per_kw", "annual_om_ratio",
            "soc_min", "soc_max", "cycle_life", "is_default_candidate", "ems_package_name",
        ]
        ws.append(headers)
        ws.append(["启用", "厂家", "型号", "额定功率", "额定容量", "时长", "电芯", "安全等级", "效率", "容量单价", "功率单价", "年运维比例", "SOC下限", "SOC上限", "循环寿命", "默认候选", "EMS包"])
        for idx, record in enumerate(records, start=1):
            rated_power = self._safe_float(record.get("rated_power_kw"), 0.0)
            rated_energy = self._safe_float(record.get("rated_energy_kwh"), 0.0)
            duration = self._safe_float(record.get("duration_hour"), 0.0)
            if duration <= 0 and rated_power > 0 and rated_energy > 0:
                duration = rated_energy / rated_power
            ws.append(
                [
                    1 if self._safe_bool(record.get("enabled"), True) else 0,
                    str(record.get("vendor") or "default_vendor"),
                    str(record.get("model") or f"storage_model_{idx}"),
                    rated_power or 100.0,
                    rated_energy or (rated_power or 100.0) * (duration or 2.0),
                    duration or 2.0,
                    str(record.get("battery_chemistry") or "LFP"),
                    str(record.get("manual_safety_grade") or record.get("safety_level") or "medium"),
                    self._safe_float(record.get("efficiency_pct"), 90.0),
                    self._safe_float(record.get("energy_unit_price_yuan_per_kwh"), 1000.0),
                    self._safe_float(record.get("power_related_capex_yuan_per_kw"), 0.0),
                    0.02,
                    self._safe_float(record.get("soc_min"), 0.10),
                    self._safe_float(record.get("soc_max"), 0.90),
                    self._safe_int(record.get("cycle_life"), 6000),
                    1 if self._safe_bool(record.get("is_default_candidate"), True) else 0,
                    str(record.get("ems_package_name") or record.get("ems_package") or ""),
                ]
            )

        ems = wb.create_sheet("EMS控制包库")
        ems.append(["ems_package_name", "capex_addon_yuan", "annual_maintenance_yuan"])
        ems.append(["EMS包名称", "一次性附加投资", "年度维护费用"])
        wb.save(path)

    def _build_solver_command(
        self,
        registry_path: Path,
        strategy_path: Path | None,
        output_dir: Path,
        dss_master_path: Path,
        project: dict[str, Any],
        selected_target_id: str | None = None,
    ) -> dict[str, Any]:
        solve_config = project.get("solve_config") if isinstance(project.get("solve_config"), dict) else {}
        extra = solve_config.get("extra") if isinstance(solve_config.get("extra"), dict) else {}
        population_size = self._safe_int(extra.get("population_size"), 16)
        generations = self._safe_int(extra.get("generations"), 8)

        args = [
            "--registry", str(registry_path.resolve()),
            "--strategy-library", str(strategy_path.resolve()) if strategy_path else "",
            "--output-dir", str(output_dir.resolve()),
            "--population-size", str(population_size),
            "--generations", str(generations),
        ]
        if selected_target_id:
            args.extend(["--target-id", selected_target_id])
        args.extend(["--enable-opendss-oracle", "--dss-master-path", str(dss_master_path.resolve())])
        return {
            "entry": "main.py",
            "args": args,
            "registry_path": str(registry_path.resolve()),
            "strategy_library_path": str(strategy_path.resolve()) if strategy_path else None,
            "output_dir": str(output_dir.resolve()),
            "dss_master_path": str(dss_master_path.resolve()),
        }

    def _asset_path(self, asset: dict[str, Any] | None) -> Path | None:
        if not isinstance(asset, dict):
            return None
        stored_path = asset.get("metadata", {}).get("stored_path") if isinstance(asset.get("metadata"), dict) else None
        if not stored_path:
            return None
        path = Path(str(stored_path))
        return path if path.exists() else None

    def _safe_name(self, value: str) -> str:
        chars = []
        for ch in value.strip():
            if ch.isalnum() or ch in {"_", "-"}:
                chars.append(ch)
            else:
                chars.append("_")
        return "".join(chars).strip("_") or "unnamed"

    def _dss_safe_name(self, value: str) -> str:
        chars = []
        for ch in value.strip():
            if ch.isalnum() or ch in {"_"}:
                chars.append(ch)
            else:
                chars.append("_")
        return "".join(chars).strip("_") or "unnamed"

    def _dss_bus_name(self, node: dict[str, Any], node_id: int) -> str:
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        explicit = str(params.get("dss_bus_name") or params.get("bus_name") or "").strip()
        if explicit:
            return self._dss_safe_name(explicit)
        if node_id > 0:
            return self._dss_safe_name(f"n{node_id}")
        return self._dss_safe_name(str(node.get("id") or "load"))

    def _dss_load_name(self, node: dict[str, Any], node_id: int) -> str:
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        explicit = str(params.get("dss_load_name") or params.get("load_name") or "").strip()
        if explicit:
            return self._dss_safe_name(explicit)
        if node_id > 0:
            return self._dss_safe_name(f"LD{node_id:02d}")
        return self._dss_safe_name(str(node.get("id") or "load"))

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            if value in (None, ""):
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def _normalize_distribution_base_kv(self, value: Any) -> float:
        kv = self._safe_float(value, 0.0)
        legacy_ln = 10.0 / math.sqrt(3.0)
        if kv > 0 and abs(kv - legacy_ln) <= max(0.02, legacy_ln * 0.03):
            return 10.0
        return kv

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            if value in (None, ""):
                return int(default)
            return int(float(value))
        except Exception:
            return int(default)

    def _safe_bool(self, value: Any, default: bool) -> bool:
        if value in (None, ""):
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "是", "启用"}:
            return True
        if text in {"0", "false", "no", "n", "off", "否", "停用"}:
            return False
        return bool(default)

    def _is_distribution_transformer_node(self, node: dict[str, Any]) -> bool:
        node_type = str(node.get("type") or "").strip().lower()
        if node_type == "distribution_transformer":
            return True
        if node_type != "transformer":
            return False
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        role = str(params.get("transformer_role") or params.get("role") or "").strip().lower()
        return role in {"distribution", "distribution_transformer", "customer_distribution"} or self._safe_bool(
            params.get("is_distribution_transformer"),
            False,
        )

    def _economic_param(
        self,
        params: dict[str, Any],
        economic_params: dict[str, Any],
        key: str,
        default: Any,
    ) -> Any:
        if key in economic_params and economic_params.get(key) not in (None, ""):
            return economic_params.get(key)
        return params.get(key, default)

    def _project_dir(self, project_id: str) -> Path:
        return self.data_root / project_id

    def _project_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def _load_project(self, project_id: str) -> dict[str, Any]:
        if self.project_service is not None and hasattr(self.project_service, "load_project"):
            project = self.project_service.load_project(project_id)
            if isinstance(project, dict):
                return project
            if hasattr(project, "model_dump"):
                return project.model_dump(mode="json")
            if hasattr(project, "dict"):
                return project.dict()

        project_file = self._project_file(project_id)
        if not project_file.exists():
            return {
                "project_id": project_id,
                "project_name": project_id,
                "network": {"nodes": [], "edges": [], "economic_parameters": {}},
            }
        return json.loads(project_file.read_text(encoding="utf-8"))

    def _extract_topology(self, project: dict[str, Any]) -> dict[str, Any]:
        network = project.get("network") if isinstance(project.get("network"), dict) else {}
        nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
        edges = network.get("edges") if isinstance(network.get("edges"), list) else []
        economic_params = network.get("economic_parameters") if isinstance(network.get("economic_parameters"), dict) else {}
        return {"nodes": nodes, "edges": edges, "economic_parameters": economic_params}

    def _build_warnings(self, topology: dict[str, Any]) -> list[str]:
        return list(self._validate_topology(topology)["warnings"])

    def _build_errors(self, topology: dict[str, Any]) -> list[str]:
        return list(self._validate_topology(topology)["errors"])

    def _validate_topology(self, topology: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        nodes = topology["nodes"]
        edges = topology["edges"]

        if not nodes:
            warnings.append("当前项目暂无节点。")
        if not edges:
            warnings.append("当前项目暂无线路。")

        grid_nodes = [node for node in nodes if str(node.get("type")).strip().lower() in {"grid", "source"}]
        transformer_nodes = [
            node
            for node in nodes
            if str(node.get("type")).strip().lower() == "transformer" and not self._is_distribution_transformer_node(node)
        ]
        load_nodes = [node for node in nodes if str(node.get("type")).strip().lower() == "load"]

        if not grid_nodes:
            errors.append("拓扑缺少电源/电网节点，无法生成完整 OpenDSS Circuit/Source。")
        if not transformer_nodes:
            errors.append("拓扑缺少主变节点，无法建立 sourcebus 到低压侧母线的电气连接。")
        if not load_nodes:
            errors.append("拓扑缺少负荷节点，无法生成 node_registry.xlsx。")

        node_id_values = [str(node.get("id")) for node in nodes if node.get("id") is not None]
        duplicates = self._find_duplicates(node_id_values)
        for duplicate in duplicates:
            errors.append(f"节点 id 重复：{duplicate}。")

        node_ids = {str(node.get("id")) for node in nodes}
        node_map = {str(node.get("id")): node for node in nodes if node.get("id") is not None}

        load_node_ids: list[str] = []
        load_dss_names: list[str] = []
        bus_names: list[str] = []
        legacy_phase_seen = False
        for node in nodes:
            node_id = str(node.get("id") or "")
            node_type = str(node.get("type") or "").strip().lower()
            params = node.get("params") if isinstance(node.get("params"), dict) else {}
            phases = self._safe_int(params.get("phases"), 3)
            if phases != 3:
                legacy_phase_seen = True

            if node_type not in {"grid", "source"}:
                bus = self._dss_bus_name(node, self._safe_int(params.get("node_id"), 0))
                bus_names.append(bus)
                if not str(params.get("dss_bus_name") or params.get("bus_name") or "").strip():
                    warnings.append(f"节点 {node.get('name') or node_id} 未填写 dss_bus_name，Build 将按规则自动生成。")

            if node_type == "load":
                registry_node_id = str(params.get("node_id") or "").strip()
                if registry_node_id:
                    load_node_ids.append(registry_node_id)
                else:
                    warnings.append(f"负荷节点 {node.get('name') or node_id} 未填写 node_id，registry 将按负荷顺序补齐。")

                load_name = self._dss_load_name(node, self._safe_int(params.get("node_id"), 0))
                load_dss_names.append(load_name)
                if not str(params.get("dss_load_name") or params.get("load_name") or "").strip():
                    warnings.append(f"负荷节点 {node.get('name') or node_id} 未填写 dss_load_name，Build 将按 node_id 自动生成。")

                target_kv = self._safe_float(params.get("target_kv_ln"), 0.0)
                if target_kv <= 0:
                    errors.append(f"负荷节点 {node.get('name') or node_id} 缺少基准电压。")
                if self._safe_float(params.get("design_kw"), 0.0) <= 0:
                    warnings.append(f"负荷节点 {node.get('name') or node_id} 的设计负荷 design_kw 未设置或为 0。")

        for duplicate in self._find_duplicates(load_node_ids):
            errors.append(f"负荷 node_id 重复：{duplicate}。")
        for duplicate in self._find_duplicates(load_dss_names):
            errors.append(f"OpenDSS 负荷名重复：{duplicate}。")
        for duplicate in self._find_duplicates(bus_names):
            warnings.append(f"多个可视化节点映射到同一 OpenDSS 母线：{duplicate}，请确认这不是误填。")

        active_adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        active_edge_count = 0
        supported_linecodes = set(self.dss_builder.LINE_CODES.keys())
        for edge in edges:
            edge_id = str(edge.get("id") or "")
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_ids:
                errors.append(f"线路 {edge_id} 起点无效。")
                continue
            if to_node_id not in node_ids:
                errors.append(f"线路 {edge_id} 终点无效。")
                continue

            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            linecode = str(params.get("linecode") or params.get("line_code") or "").strip()
            from_node = node_map.get(from_node_id, {})
            to_node = node_map.get(to_node_id, {})
            is_service_line = (
                self._is_distribution_transformer_node(from_node) or 
                self._is_distribution_transformer_node(to_node)
            )
            if not linecode and not is_service_line:
                warnings.append(f"线路 {edge_id} 未选择 linecode，Build 将使用默认值 LC_MAIN。")
            elif linecode and linecode not in supported_linecodes:
                errors.append(f"线路 {edge_id} 使用了未定义的 linecode={linecode}。")

            phases = self._safe_int(params.get("phases"), 0)
            if phases != 3:
                legacy_phase_seen = True

            if self._safe_float(params.get("length_km"), 0.0) <= 0:
                errors.append(f"线路 {edge_id} 长度 length_km 必须大于 0。")
            if self._safe_float(params.get("rated_current_a"), 0.0) <= 0:
                warnings.append(f"线路 {edge_id} 额定电流 rated_current_a 未设置或为 0。")

            from_phases = self._safe_int((node_map[from_node_id].get("params") or {}).get("phases") if isinstance(node_map[from_node_id].get("params"), dict) else None, 3)
            to_phases = self._safe_int((node_map[to_node_id].get("params") or {}).get("phases") if isinstance(node_map[to_node_id].get("params"), dict) else None, 3)
            if phases in {1, 3} and (from_phases in {1, 3} and to_phases in {1, 3}) and (phases != from_phases or phases != to_phases):
                warnings.append(f"线路 {edge_id} 相数与端点节点相数不一致。")

            active = self._safe_bool(params.get("enabled"), True) and not self._safe_bool(params.get("normally_open"), False)
            if active:
                active_edge_count += 1
                active_adjacency[from_node_id].add(to_node_id)
                active_adjacency[to_node_id].add(from_node_id)

        if legacy_phase_seen:
            warnings.append("检测到旧拓扑中存在非三相相数设置；Build 将统一按三相平衡 OpenDSS 模型构建。")

        roots = {str(node.get("id")) for node in [*grid_nodes, *transformer_nodes] if node.get("id") is not None}
        visited = self._walk_graph(active_adjacency, roots)
        disconnected = sorted(node_id for node_id in node_ids if node_id not in visited)
        for node_id in disconnected[:12]:
            node = node_map.get(node_id, {})
            errors.append(f"节点 {node.get('name') or node_id} 未通过闭合线路连接到电源/主变。")
        if len(disconnected) > 12:
            errors.append(f"另有 {len(disconnected) - 12} 个节点未连接到电源/主变。")

        return {
            "ready_for_build": len(nodes) > 0 and len(errors) == 0,
            "warnings": warnings,
            "errors": errors,
            "grid_count": len(grid_nodes),
            "transformer_count": len(transformer_nodes),
            "load_count": len(load_nodes),
            "active_edge_count": active_edge_count,
            "disconnected_count": len(disconnected),
        }

    def _find_duplicates(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for value in values:
            key = str(value).strip()
            if not key:
                continue
            if key in seen:
                duplicates.add(key)
            seen.add(key)
        return sorted(duplicates)

    def _walk_graph(self, adjacency: dict[str, set[str]], roots: set[str]) -> set[str]:
        visited: set[str] = set()
        stack = [root for root in roots if root in adjacency]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(sorted(adjacency.get(current, set()) - visited))
        return visited
