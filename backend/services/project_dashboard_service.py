from __future__ import annotations

from typing import Any, Dict, Optional

from models.project_model import ProjectDashboardData, ProjectDashboardStepStatus, WorkflowStepCard
from services.build_export_service import BuildExportService
from services.project_model_service import ProjectModelService
from services.solver_execution_service import SolverExecutionService


class ProjectDashboardService:
    def __init__(
        self,
        project_service: Optional[ProjectModelService] = None,
        build_service: Optional[BuildExportService] = None,
        solver_service: Optional[SolverExecutionService] = None,
    ) -> None:
        self.project_service = project_service or ProjectModelService()
        self.build_service = build_service or BuildExportService(project_service=self.project_service)
        self.solver_service = solver_service or SolverExecutionService(project_service=self.project_service)

    def get_dashboard(self, project_id: str) -> ProjectDashboardData:
        project = self.project_service.load_project(project_id)

        node_count = len(project.network.nodes)
        edge_count = len(project.network.edges)
        load_nodes = [
            n for n in project.network.nodes
            if str(getattr(n.type, "value", n.type)) == "load"
        ]
        runtime_bound = [
            n for n in load_nodes
            if n.runtime_binding
            and n.runtime_binding.year_map_file_id
            and n.runtime_binding.model_library_file_id
        ]

        build_manifest_exists = (
            self.project_service._project_dir(project_id)
            / "build"
            / "manifest"
            / "build_manifest.json"
        ).exists()

        build_ready = False
        try:
            preview = self.build_service.preview_build(project_id)
            summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
            build_ready = bool(summary.get("ready_for_build"))
        except Exception:
            preview = {}

        latest_solver_status: str | None = None
        latest_summary: Dict[str, Any] = {}

        try:
            latest = self.solver_service.get_latest_task(project_id)
            if latest:
                latest_solver_status = str(latest.get("status")) if latest.get("status") is not None else None

                metadata = latest.get("metadata") or {}
                rows = metadata.get("summary_rows") or []
                if rows:
                    best = rows[0]
                    latest_summary = {
                        "scenario": best.get("scenario") or best.get("scenario_name"),
                        "node": best.get("node") or best.get("node_id"),
                        "strategy_id": best.get("strategy_id") or best.get("scheme_label"),
                        "strategy_name": best.get("strategy_name") or best.get("strategy_id"),
                        "power_kw": best.get("power_kw") or best.get("rated_power_kw"),
                        "energy_kwh": best.get("energy_kwh") or best.get("rated_energy_kwh"),
                        "duration_h": best.get("duration_h"),
                        "npv_wan": best.get("npv_wan"),
                        "payback_years": best.get("payback_years") or best.get("simple_payback_years"),
                        "irr_percent": best.get("irr_percent"),
                        "annual_equivalent_cycles": best.get("annual_equivalent_cycles"),
                    }
        except Exception:
            pass

        if not latest_summary:
            try:
                summary_payload = self.solver_service.get_summary(project_id)
                summary_rows = summary_payload.get("summary_rows") or []
                overall_best = summary_payload.get("overall_best_schemes") or []

                if summary_rows:
                    best = summary_rows[0]
                    latest_summary = {
                        "scenario": best.get("scenario") or best.get("scenario_name"),
                        "node": best.get("node") or best.get("node_id"),
                        "strategy_id": best.get("strategy_id") or best.get("scheme_label"),
                        "strategy_name": best.get("strategy_name") or best.get("strategy_id"),
                        "power_kw": best.get("power_kw") or best.get("rated_power_kw"),
                        "energy_kwh": best.get("energy_kwh") or best.get("rated_energy_kwh"),
                        "duration_h": best.get("duration_h"),
                        "npv_wan": best.get("npv_wan"),
                        "payback_years": best.get("payback_years") or best.get("simple_payback_years"),
                        "irr_percent": best.get("irr_percent"),
                        "annual_equivalent_cycles": best.get("annual_equivalent_cycles"),
                    }
                elif overall_best:
                    best = overall_best[0]
                    latest_summary = {
                        "scenario": best.get("scenario_name") or best.get("internal_model_id"),
                        "node": best.get("node_id"),
                        "strategy_id": best.get("strategy_id"),
                        "strategy_name": best.get("strategy_name") or best.get("strategy_id"),
                        "power_kw": best.get("rated_power_kw"),
                        "energy_kwh": best.get("rated_energy_kwh"),
                        "duration_h": best.get("duration_h"),
                        "npv_wan": (float(best.get("npv_yuan")) / 10000.0) if best.get("npv_yuan") is not None else None,
                        "payback_years": best.get("simple_payback_years"),
                        "irr_percent": (float(best.get("irr")) * 100.0) if best.get("irr") is not None else None,
                        "annual_equivalent_cycles": best.get("annual_equivalent_full_cycles"),
                    }
            except Exception:
                pass

        def step_status(
            condition_ready: bool,
            condition_done: bool = False,
            condition_failed: bool = False,
        ) -> ProjectDashboardStepStatus:
            if condition_failed:
                return ProjectDashboardStepStatus.FAILED
            if condition_done:
                return ProjectDashboardStepStatus.COMPLETED
            if condition_ready:
                return ProjectDashboardStepStatus.READY
            return ProjectDashboardStepStatus.NOT_STARTED

        has_tariff = project.tariff.asset is not None
        has_device_library = bool(project.device_library.records)
        topology_done = node_count > 0 and edge_count > 0
        assets_done = (
            has_tariff
            and has_device_library
            and len(runtime_bound) == len(load_nodes)
            and len(load_nodes) > 0
        )

        if latest_solver_status == "completed":
            solver_step_status = ProjectDashboardStepStatus.COMPLETED
        elif latest_solver_status in {"queued", "running"}:
            solver_step_status = ProjectDashboardStepStatus.IN_PROGRESS
        elif latest_solver_status == "failed":
            solver_step_status = ProjectDashboardStepStatus.FAILED
        else:
            solver_step_status = ProjectDashboardStepStatus.NOT_STARTED

        results_step_status = (
            ProjectDashboardStepStatus.COMPLETED if bool(latest_summary) else ProjectDashboardStepStatus.NOT_STARTED
        )

        # When historical results exist and no task is running, all steps show as completed
        # (the default view reflects the latest historical task's results).
        show_all_completed = bool(latest_summary) and latest_solver_status not in {"running", "queued"}

        steps = [
            WorkflowStepCard(
                key="overview",
                label="项目总览",
                status=ProjectDashboardStepStatus.COMPLETED,
                route=f"/projects/{project_id}/overview",
            ),
            WorkflowStepCard(
                key="topology",
                label="拓扑建模",
                status=ProjectDashboardStepStatus.COMPLETED if show_all_completed else step_status(topology_done, topology_done),
                route=f"/projects/{project_id}/topology",
                counts={"nodes": node_count, "edges": edge_count, "load_nodes": len(load_nodes)},
            ),
            WorkflowStepCard(
                key="assets",
                label="资产绑定",
                status=ProjectDashboardStepStatus.COMPLETED if show_all_completed else step_status(assets_done, assets_done),
                route=f"/projects/{project_id}/assets",
                counts={
                    "runtime_bound": len(runtime_bound),
                    "runtime_total": len(load_nodes),
                    "has_tariff": has_tariff,
                    "has_device_library": has_device_library,
                },
            ),
            WorkflowStepCard(
                key="build",
                label="构建校验",
                status=ProjectDashboardStepStatus.COMPLETED if show_all_completed else step_status(build_ready, build_manifest_exists),
                route=f"/projects/{project_id}/build",
                counts={"build_ready": build_ready, "build_manifest_exists": build_manifest_exists},
            ),
            WorkflowStepCard(
                key="solver",
                label="计算运行",
                status=solver_step_status,
                route=f"/projects/{project_id}/solver",
                detail=latest_solver_status,
            ),
            WorkflowStepCard(
                key="results",
                label="结果展示",
                status=results_step_status,
                route=f"/projects/{project_id}/results",
            ),
        ]

        return ProjectDashboardData(
            project_id=project_id,
            project_name=project.project_name,
            description=project.description,
            node_count=node_count,
            edge_count=edge_count,
            load_node_count=len(load_nodes),
            runtime_bound_load_count=len(runtime_bound),
            has_tariff=has_tariff,
            has_device_library=has_device_library,
            build_ready=build_ready,
            build_manifest_exists=build_manifest_exists,
            latest_solver_status=latest_solver_status,
            latest_summary=latest_summary,
            steps=steps,
        )
