"""Aggregate project + solver data for the energy storage configuration proposal report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.project_model import NodeType


def _number(value: Any) -> Optional[float]:
    try:
        v = float(value)
        if not _isfinite(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _isfinite(v: float) -> bool:
    import math

    return math.isfinite(v)


class ReportDataService:
    def __init__(self, project_service: Any, solver_service: Any, inference_service: Any = None):
        self._project_service = project_service
        self._solver_service = solver_service
        self._inference_service = inference_service

    def assemble(self, project_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        project = self._load_project(project_id)
        deliverables = self._solver_service.get_report_deliverables(project_id, task_id) if self._solver_service else {}
        if not isinstance(deliverables, dict):
            deliverables = {}
        cashflow = self._solver_service.get_report_cashflow(project_id, task_id) if self._solver_service else []
        if not isinstance(cashflow, list):
            cashflow = []
        summary = self._solver_service.get_summary(project_id, task_id) if self._solver_service else {}
        if not isinstance(summary, dict):
            summary = {}
        best = summary.get("best_result_summary") if isinstance(summary.get("best_result_summary"), dict) else {}

        return {
            "project_meta": self._build_project_meta(project),
            "devices": self._build_devices(project),
            "configuration": self._build_configuration(deliverables, best),
            "operation": self._build_operation(deliverables, best),
            "financial": self._build_financial(deliverables, best, cashflow),
            "network_impact": self._build_network_impact(deliverables),
            "run_health": self._build_run_health(deliverables),
            "warnings": self._collect_warnings(deliverables),
            "task_meta": self._build_task_meta(project_id, task_id),
            "source_files": self._build_source_files(project_id, task_id),
            "assumptions": self._build_assumptions(project, deliverables),
            "load_profile": self._build_load_profile(project, project_id, best),
            "charts": self._build_charts(project_id, task_id),
            "candidate_comparison": self._build_candidate_comparison(project_id, task_id),
            "data_quality": self._build_data_quality(deliverables),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # project meta
    # ------------------------------------------------------------------
    def _load_project(self, project_id: str):
        try:
            return self._project_service.load_project(project_id)
        except Exception:
            return None

    def _build_project_meta(self, project) -> Dict[str, Any]:
        if project is None:
            return {}
        network = getattr(project, "network", None)
        nodes = getattr(network, "nodes", None) or []
        edges = getattr(network, "edges", None) or []
        tariff = getattr(project, "tariff", None)
        return {
            "project_name": getattr(project, "project_name", "") or "",
            "description": getattr(project, "description", None),
            "created_at": getattr(project, "created_at", None),
            "version": getattr(project, "version", "2.1.0") or "2.1.0",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "load_node_count": sum(1 for n in nodes if getattr(n, "type", None) == NodeType.LOAD),
            "has_tariff": getattr(tariff, "asset", None) is not None if tariff else False,
            "tariff_year": getattr(tariff, "tariff_year", None) if tariff else None,
        }

    # ------------------------------------------------------------------
    # devices
    # ------------------------------------------------------------------
    def _build_devices(self, project) -> List[Dict[str, Any]]:
        if project is None:
            return []
        device_library = getattr(project, "device_library", None)
        records = getattr(device_library, "records", None) or []
        devices = []
        for rec in records:
            if not getattr(rec, "enabled", True):
                continue
            devices.append(
                {
                    "vendor": getattr(rec, "vendor", None),
                    "model": getattr(rec, "model", None),
                    "series_name": getattr(rec, "series_name", None),
                    "device_family": getattr(rec, "device_family", None),
                    "battery_chemistry": getattr(rec, "battery_chemistry", None),
                    "rated_power_kw": _number(getattr(rec, "rated_power_kw", None)),
                    "rated_energy_kwh": _number(getattr(rec, "rated_energy_kwh", None)),
                    "usable_energy_kwh_at_fat": _number(getattr(rec, "usable_energy_kwh_at_fat", None)),
                    "duration_hour": _number(getattr(rec, "duration_hour", None)),
                    "dc_voltage_range_v": getattr(rec, "dc_voltage_range_v", None),
                    "ac_grid_voltage_v": getattr(rec, "ac_grid_voltage_v", None),
                    "cooling_type": getattr(rec, "cooling_type", None),
                    "fire_detection": getattr(rec, "fire_detection", None),
                    "fire_suppression": getattr(rec, "fire_suppression", None),
                    "safety_level": getattr(rec, "safety_level", None),
                    "cycle_life": getattr(rec, "cycle_life", None),
                    "soc_min": _number(getattr(rec, "soc_min", None)),
                    "soc_max": _number(getattr(rec, "soc_max", None)),
                    "efficiency_pct": _number(getattr(rec, "efficiency_pct", None)),
                    "ip_system": getattr(rec, "ip_system", None),
                    "corrosion_grade": getattr(rec, "corrosion_grade", None),
                    "install_mode": getattr(rec, "install_mode", None),
                    "dimension_w_mm": _number(getattr(rec, "dimension_w_mm", None)),
                    "dimension_d_mm": _number(getattr(rec, "dimension_d_mm", None)),
                    "dimension_h_mm": _number(getattr(rec, "dimension_h_mm", None)),
                    "weight_kg": _number(getattr(rec, "weight_kg", None)),
                    "price_yuan_per_wh": _number(getattr(rec, "price_yuan_per_wh", None)),
                    "energy_unit_price_yuan_per_kwh": _number(getattr(rec, "energy_unit_price_yuan_per_kwh", None)),
                    "power_related_capex_yuan_per_kw": _number(getattr(rec, "power_related_capex_yuan_per_kw", None)),
                    "communication_protocol": getattr(rec, "communication_protocol", None),
                    "supports_black_start": getattr(rec, "supports_black_start", None),
                    "supports_offgrid_microgrid": getattr(rec, "supports_offgrid_microgrid", None),
                }
            )
        return devices

    # ------------------------------------------------------------------
    # configuration
    # ------------------------------------------------------------------
    def _build_configuration(self, deliverables: Dict[str, Any], best: Dict[str, Any]) -> Dict[str, Any]:
        cfg = deliverables.get("configuration") if isinstance(deliverables.get("configuration"), dict) else {}
        return {
            "target_id": cfg.get("target_id") or best.get("internal_model_id"),
            "target_bus": cfg.get("target_bus") or best.get("target_bus"),
            "strategy_id": cfg.get("strategy_id") or best.get("strategy_id"),
            "strategy_name": cfg.get("strategy_name") or best.get("strategy_name"),
            "rated_power_kw": _number(cfg.get("rated_power_kw")) or _number(best.get("rated_power_kw")),
            "rated_energy_kwh": _number(cfg.get("rated_energy_kwh")) or _number(best.get("rated_energy_kwh")),
            "duration_h": _number(cfg.get("duration_h")) or _number(best.get("duration_h")),
            "capacity_factor": _number(best.get("first_year_capacity_factor")),
            "background_load_policy": cfg.get("background_load_policy"),
        }

    # ------------------------------------------------------------------
    # operation
    # ------------------------------------------------------------------
    def _build_operation(self, deliverables: Dict[str, Any], best: Dict[str, Any]) -> Dict[str, Any]:
        op = deliverables.get("operation") if isinstance(deliverables.get("operation"), dict) else {}
        annual = op.get("annual_metrics") if isinstance(op.get("annual_metrics"), dict) else {}
        return {
            "annual_equivalent_full_cycles": _number(annual.get("equivalent_full_cycles")) or _number(best.get("annual_equivalent_full_cycles")),
            "annual_battery_throughput_kwh": _number(annual.get("battery_throughput_kwh")) or _number(best.get("annual_battery_throughput_kwh")),
            "capacity_factor": _number(best.get("first_year_capacity_factor")),
        }

    # ------------------------------------------------------------------
    # financial
    # ------------------------------------------------------------------
    def _build_financial(
        self, deliverables: Dict[str, Any], best: Dict[str, Any], cashflow: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        fin = deliverables.get("financial") if isinstance(deliverables.get("financial"), dict) else {}
        core = fin.get("core_metrics") if isinstance(fin.get("core_metrics"), dict) else {}

        # revenue breakdown
        rev = fin.get("annual_revenue_breakdown_yuan") if isinstance(fin.get("annual_revenue_breakdown_yuan"), dict) else {}
        cost = fin.get("annual_cost_breakdown_yuan") if isinstance(fin.get("annual_cost_breakdown_yuan"), dict) else {}

        # audit ledger
        ledger = fin.get("annual_audit_ledger") if isinstance(fin.get("annual_audit_ledger"), dict) else {}
        ledger_items = ledger.get("items") if isinstance(ledger.get("items"), list) else []
        audit_summary = fin.get("audit_ledger_summary") if isinstance(fin.get("audit_ledger_summary"), dict) else {}

        # cashflow – top 25 rows
        cashflow_out = []
        for row in cashflow[:25]:
            cashflow_out.append(
                {
                    "year": _number(row.get("year")),
                    "revenue_yuan": _number(row.get("total_revenue_yuan")),
                    "op_cost_yuan": _number(row.get("total_operating_cost_yuan")),
                    "net_cashflow_yuan": _number(row.get("net_cashflow_yuan")),
                    "cumulative_undiscounted_yuan": _number(row.get("cumulative_undiscounted_cashflow_yuan")),
                    "discounted_net_yuan": _number(row.get("discounted_net_cashflow_yuan")),
                    "cumulative_discounted_yuan": _number(row.get("cumulative_discounted_cashflow_yuan")),
                }
            )

        return {
            "core": {
                "npv_yuan": _number(core.get("npv_yuan")) or _number(best.get("npv_yuan")),
                "irr": _number(core.get("irr")) or _number(best.get("irr")),
                "simple_payback_years": _number(core.get("simple_payback_years")) or _number(best.get("simple_payback_years")),
                "discounted_payback_years": _number(core.get("discounted_payback_years")) or _number(best.get("discounted_payback_years")),
                "initial_investment_yuan": _number(core.get("initial_investment_yuan")) or _number(best.get("initial_investment_yuan")),
                "annualized_net_cashflow_yuan": _number(core.get("annualized_net_cashflow_yuan")) or _number(best.get("annualized_net_cashflow_yuan")),
                "lcoe_yuan_per_kwh": _number(core.get("lcoe_yuan_per_kwh")),
                "roi_pct": _number(core.get("roi_pct")),
                "revenue_breakdown": {
                    "arbitrage": _number(rev.get("arbitrage")) or _number(best.get("annual_arbitrage_revenue_yuan")),
                    "demand_saving": _number(rev.get("demand_saving")) or _number(best.get("annual_demand_saving_yuan")),
                    "capacity": _number(rev.get("capacity")) or _number(best.get("annual_capacity_revenue_yuan")),
                    "loss_reduction": _number(rev.get("loss_reduction")) or _number(best.get("annual_loss_reduction_revenue_yuan")),
                    "auxiliary_service": _number(rev.get("auxiliary_service_net")) or _number(best.get("annual_auxiliary_service_revenue_yuan")),
                },
                "cost_breakdown": {
                    "degradation": _number(cost.get("degradation")) or _number(best.get("annual_degradation_cost_yuan")),
                    "o_and_m": _number(cost.get("om")) or _number(best.get("annual_om_cost_yuan")),
                    "replacement": _number(cost.get("replacement_equivalent")) or _number(best.get("annual_replacement_equivalent_cost_yuan")),
                    "transformer_penalty": _number(cost.get("transformer_penalty")),
                    "voltage_penalty": _number(cost.get("voltage_penalty")),
                },
            },
            "audit_ledger_items": [
                {
                    "name": str(item.get("name", "")),
                    "category": str(item.get("category", "")),
                    "amount_yuan": _number(item.get("amount_yuan")),
                    "quantity": _number(item.get("quantity")),
                    "unit_price": _number(item.get("unit_price")),
                    "anomaly": str(item.get("anomaly", "")) if item.get("anomaly") else None,
                }
                for item in ledger_items[:50]
            ],
            "audit_ledger_anomalies": [
                {
                    "item": str(a.get("item", "")),
                    "field": str(a.get("field", "")),
                    "level": str(a.get("level", "warning")),
                    "message": str(a.get("message", "")),
                }
                for a in (audit_summary.get("anomalies") or [])
            ],
            "audit_ledger_item_count": int(audit_summary.get("item_count") or len(ledger_items)),
            "audit_ledger_anomaly_count": int(audit_summary.get("anomaly_count") or 0),
            "cashflow_table": cashflow_out,
        }

    # ------------------------------------------------------------------
    # network impact
    # ------------------------------------------------------------------
    def _build_network_impact(self, deliverables: Dict[str, Any]) -> Dict[str, Any]:
        ni = deliverables.get("network_impact") if isinstance(deliverables.get("network_impact"), dict) else {}
        risk_details = ni.get("risk_details") if isinstance(ni.get("risk_details"), dict) else {}
        return {
            "target_area_conclusion": ni.get("target_area_conclusion"),
            "attribution_summary": ni.get("attribution_summary"),
            "risk_classification": ni.get("risk_classification_summary", {}).get("items") or [],
            "voltage_top_risks": risk_details.get("voltage_top_risks") or [],
            "line_top_risks": risk_details.get("line_top_risks") or [],
            "transformer_top_risks": ni.get("transformer_top_risks") or [],
            "data_quality": ni.get("data_quality"),
            "baseline": ni.get("baseline"),
            "with_storage": ni.get("with_storage"),
            "delta": ni.get("delta"),
        }

    # ------------------------------------------------------------------
    # run health
    # ------------------------------------------------------------------
    def _build_run_health(self, deliverables: Dict[str, Any]) -> Dict[str, Any]:
        rh = deliverables.get("run_health") if isinstance(deliverables.get("run_health"), dict) else {}
        issues = rh.get("issues") if isinstance(rh.get("issues"), list) else []
        summary = rh.get("summary") if isinstance(rh.get("summary"), dict) else {}
        return {
            "status": str(rh.get("status") or ""),
            "total_issues": int(summary.get("issue_count") or len(issues)),
            "warning_count": int(summary.get("warning_count") or 0),
            "critical_count": int(summary.get("critical_count") or 0),
            "issues": [
                {
                    "code": str(issue.get("code", "")),
                    "message": str(issue.get("message", "")),
                    "severity": str(issue.get("severity", "")),
                    "level": str(issue.get("level", "warning")),
                    "reason": str(issue.get("reason", "")),
                    "impact": str(issue.get("impact", "")),
                    "suggestion": str(issue.get("suggestion", "")),
                    "related_section": str(issue.get("related_section", "")),
                }
                for issue in issues
            ],
        }

    # ------------------------------------------------------------------
    # warnings
    # ------------------------------------------------------------------
    _STATUS_LABELS: Dict[str, str] = {"warning": "有警告", "critical": "严重异常", "passed": "通过"}

    def _collect_warnings(self, deliverables: Dict[str, Any]) -> List[str]:
        warnings: List[str] = []
        rh = deliverables.get("run_health") if isinstance(deliverables.get("run_health"), dict) else {}
        status = str(rh.get("status") or "").lower()
        if status in ("warning", "critical"):
            label = self._STATUS_LABELS.get(status, status)
            warnings.append(f"系统健康检查状态: {label}")
        ni = deliverables.get("network_impact") if isinstance(deliverables.get("network_impact"), dict) else {}
        conclusion = ni.get("target_area_conclusion") if isinstance(ni.get("target_area_conclusion"), dict) else {}
        conclusion_status = str(conclusion.get("status") or "").lower()
        if conclusion_status == "worsened":
            warnings.append("目标接入区域安全指标恶化，请关注电网影响分析章节。")
        return warnings

    # ------------------------------------------------------------------
    # task_meta
    # ------------------------------------------------------------------
    def _build_task_meta(self, project_id: str, task_id: Optional[str]) -> Dict[str, Any]:
        try:
            tasks = self._solver_service.list_tasks(project_id) if self._solver_service else []
            if not isinstance(tasks, list):
                tasks = []
            target = None
            if task_id:
                target = next((t for t in tasks if (t.get("task_id") if isinstance(t, dict) else None) == task_id), None)
            if target is None:
                target = next((t for t in tasks if isinstance(t, dict) and str(t.get("status", "")).lower() == "completed"), None)
            if target is None and tasks:
                target = tasks[-1] if isinstance(tasks[-1], dict) else None
            if not isinstance(target, dict):
                target = {}
            charts_info = {}
            if self._solver_service:
                try:
                    report_charts = self._solver_service.get_report_charts(project_id, task_id)
                    if isinstance(report_charts, dict):
                        charts_info = report_charts
                except Exception:
                    pass
            latest_task = charts_info.get("latest_task") if isinstance(charts_info.get("latest_task"), dict) else {}
            return {
                "task_id": target.get("task_id") or latest_task.get("task_id"),
                "status": target.get("status") or latest_task.get("status"),
                "started_at": target.get("started_at"),
                "completed_at": target.get("completed_at"),
                "selected_case": charts_info.get("selected_case"),
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # source_files
    # ------------------------------------------------------------------
    def _build_source_files(self, project_id: str, task_id: Optional[str]) -> List[Dict[str, Any]]:
        try:
            if not self._solver_service:
                return []
            report_charts = self._solver_service.get_report_charts(project_id, task_id)
            if not isinstance(report_charts, dict):
                return []
            source_files = report_charts.get("source_files")
            if not isinstance(source_files, dict):
                return []
            result: List[Dict[str, Any]] = []
            for group, path in source_files.items():
                result.append({"relative_path": str(path), "group": str(group)})
            return result
        except Exception:
            return []

    # ------------------------------------------------------------------
    # assumptions
    # ------------------------------------------------------------------
    def _build_assumptions(self, project, deliverables: Dict[str, Any]) -> Dict[str, Any]:
        if project is None:
            return {}
        tariff = getattr(project, "tariff", None)
        network = getattr(project, "network", None)
        econ = getattr(network, "economic_parameters", None) if network else None
        device_library = getattr(project, "device_library", None)
        records = getattr(device_library, "records", None) or []
        primary_device = None
        for rec in records:
            if getattr(rec, "enabled", True):
                primary_device = rec
                break
        # OpenDSS: prefer actual run data over project-level config
        ni = deliverables.get("network_impact") if isinstance(deliverables.get("network_impact"), dict) else {}
        dq = ni.get("data_quality") if isinstance(ni.get("data_quality"), dict) else {}
        opendss_enabled = bool(dq.get("opendss_trace_hours") or dq.get("has_opendss_loss"))
        opendss_hours = dq.get("opendss_trace_hours")
        return {
            "tariff_year": getattr(tariff, "tariff_year", None) if tariff else None,
            "discount_rate": _number(getattr(econ, "discount_rate", None)) if econ else None,
            "project_life_years": _number(getattr(econ, "project_life", None)) if econ else None,
            "soc_min": _number(getattr(primary_device, "soc_min", None)) if primary_device else None,
            "soc_max": _number(getattr(primary_device, "soc_max", None)) if primary_device else None,
            "opendss_enabled": opendss_enabled,
            "opendss_coverage_hours": _number(opendss_hours),
            "initial_soc": 0.5,
            "terminal_soc_mode": "auto" if primary_device else None,
            "safety_economy_tradeoff": _number(getattr(econ, "tradeoff_parameter", None)) if econ else None,
        }

    # ------------------------------------------------------------------
    # load_profile
    # ------------------------------------------------------------------
    def _build_load_profile(self, project, project_id: str, best: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if self._inference_service and project_id:
                rows = self._inference_service.get_inference_rows(project_id)
                if rows:
                    target_load_id = best.get("load_id") or best.get("internal_model_id")
                    target_bus = best.get("target_bus")
                    matched_row = None
                    # pass 1: exact node_id match
                    for row in rows:
                        node_id = getattr(row, "node_id", None)
                        if target_load_id and node_id == target_load_id:
                            matched_row = row
                            break
                    # pass 2: match by node_name against target_bus or target_id
                    if matched_row is None:
                        for row in rows:
                            node_name = str(getattr(row, "node_name", "") or "")
                            if (target_bus and node_name == target_bus) or (target_load_id and node_name == target_load_id):
                                matched_row = row
                                break
                    # pass 3: fallback — if only one load node, use it; otherwise unable to determine
                    if matched_row is None and len(rows) == 1:
                        matched_row = rows[0]
                    if matched_row is None:
                        return {}
                    peak = _number(getattr(matched_row, "peak_kw", None))
                    valley = _number(getattr(matched_row, "valley_kw", None))
                    mean_kw = _number(getattr(matched_row, "annual_mean_kw", None))
                    daily_energy = _number(getattr(matched_row, "mean_daily_energy_kwh", None))
                    load_factor = None
                    if peak and mean_kw and peak > 0:
                        load_factor = mean_kw / peak
                    return {
                        "peak_kw": peak,
                        "valley_kw": valley,
                        "annual_mean_kw": mean_kw,
                        "mean_daily_energy_kwh": daily_energy,
                        "load_factor": load_factor,
                        "target_node_name": getattr(matched_row, "node_name", None),
                        "target_node_id": getattr(matched_row, "node_id", None),
                    }
        except Exception:
            pass
        return {}

    # ------------------------------------------------------------------
    # charts
    # ------------------------------------------------------------------
    def _build_charts(self, project_id: str, task_id: Optional[str]) -> Dict[str, Any]:
        try:
            if not self._solver_service:
                return {}
            report_charts = self._solver_service.get_report_charts(project_id, task_id)
            if not isinstance(report_charts, dict):
                return {}
            charts = report_charts.get("charts")
            if isinstance(charts, dict):
                return charts
            return {}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # candidate_comparison
    # ------------------------------------------------------------------
    def _build_candidate_comparison(self, project_id: str, task_id: Optional[str]) -> Dict[str, Any]:
        try:
            summary = self._solver_service.get_summary(project_id, task_id) if self._solver_service else {}
            if not isinstance(summary, dict):
                summary = {}
            best = summary.get("best_result_summary") if isinstance(summary.get("best_result_summary"), dict) else {}
            charts = self._build_charts(project_id, task_id)
            pareto = charts.get("pareto") or []
            alternatives = []
            for p in pareto[:5]:
                if not isinstance(p, dict):
                    continue
                if p.get("npvWan") == best.get("npv_yuan"):
                    continue
                alternatives.append(p)
            return {
                "recommended": best,
                "alternatives": alternatives[:4],
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # data_quality
    # ------------------------------------------------------------------
    def _build_data_quality(self, deliverables: Dict[str, Any]) -> Dict[str, Any]:
        ni = deliverables.get("network_impact") if isinstance(deliverables.get("network_impact"), dict) else {}
        dq = ni.get("data_quality") if isinstance(ni.get("data_quality"), dict) else {}
        missing: List[str] = []
        degraded: List[str] = []
        if not deliverables.get("configuration"):
            missing.append("配置方案报告（configuration_report.json）")
        if not deliverables.get("financial"):
            missing.append("经济性报告（financial_report.json）")
        if not deliverables.get("network_impact"):
            missing.append("电网影响报告（network_impact_report.json）")
        if not deliverables.get("run_health"):
            missing.append("运行健康报告（run_health_report.json）")
        rh = deliverables.get("run_health") if isinstance(deliverables.get("run_health"), dict) else {}
        status = str(rh.get("status") or "").lower()
        if status in ("warning", "critical"):
            label = self._STATUS_LABELS.get(status, status)
            degraded.append(f"系统健康检查状态: {label}，部分指标未达标")
        return {
            "missing_data_flags": missing,
            "degraded_calculations": degraded,
            "opendss_enabled": dq.get("has_opendss_loss", False) or bool(dq.get("opendss_trace_hours")),
            "trace_completeness": f"{dq.get('opendss_trace_hours', '0')} 小时" if dq.get("opendss_trace_hours") else None,
        }
