from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from storage_engine_project.optimization.lemming_optimizer import LemmingOptimizationRunResult
from storage_engine_project.optimization.optimizer_bridge import OptimizerBridge
from storage_engine_project.visualization.plot_dispatch import plot_dispatch_profiles
from storage_engine_project.visualization.plot_economics import plot_financial_diagnostics
from storage_engine_project.visualization.plot_pareto import plot_pareto_front
from storage_engine_project.visualization.plot_scheme import plot_scheme_overview


def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_write_json(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(obj), f, ensure_ascii=False, indent=2)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "tolist"):
        return _json_safe(obj.tolist())
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    return obj


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _voltage_violation_pu(vmin: Any, vmax: Any) -> float:
    min_value = _to_float(vmin)
    max_value = _to_float(vmax)
    underv = 0.0 if min_value is None else max(0.0, 0.93 - min_value)
    overv = 0.0 if max_value is None else max(0.0, max_value - 1.07)
    return float(underv + overv)


def _safe_float(value: Any, default: float = 0.0) -> float:
    parsed = _to_float(value)
    return float(default) if parsed is None else float(parsed)


def _safe_sum(rows: list[dict[str, Any]], key: str) -> float:
    return float(sum(_safe_float(row.get(key)) for row in rows))


def _representative_operation_day(ann: Any) -> int:
    throughput = getattr(ann, "exec_charge_kw") + getattr(ann, "exec_discharge_kw")
    day_totals = throughput.sum(axis=1)
    if day_totals.size == 0:
        return 0
    return int(day_totals.argmax())


def _build_configuration_report(best_result: Any, case_name: str) -> dict[str, Any]:
    decision = getattr(best_result, "decision", None)
    summary = best_result.summary_dict() if hasattr(best_result, "summary_dict") else {}
    ann = getattr(best_result, "annual_operation_result", None)
    target_bus = None
    target_load = None
    if ann is not None:
        for exec_result in getattr(ann, "daily_exec_objects", None) or []:
            for trace in getattr(exec_result, "network_trace", None) or []:
                if isinstance(trace, dict):
                    target_bus = target_bus or trace.get("target_bus")
                    target_load = target_load or trace.get("target_load")
                if target_bus or target_load:
                    break
            if target_bus or target_load:
                break
    return {
        "report_type": "configuration",
        "case_name": case_name,
        "target_id": summary.get("internal_model_id") or case_name,
        "target_bus": target_bus,
        "target_load": target_load,
        "single_target_storage_flow": True,
        "background_load_policy": "仅对人工选择的目标用户配置储能；其他启用负荷作为背景负荷写入 OpenDSS，并参与每小时全网潮流计算。",
        "strategy_id": getattr(decision, "strategy_id", summary.get("strategy_id", "")),
        "rated_power_kw": _safe_float(getattr(decision, "rated_power_kw", summary.get("rated_power_kw"))),
        "rated_energy_kwh": _safe_float(getattr(decision, "rated_energy_kwh", summary.get("rated_energy_kwh"))),
        "duration_h": _safe_float(summary.get("duration_h")),
        "is_valid": bool(summary.get("is_valid", False)),
        "feasible": bool(summary.get("feasible", False)),
        "notes": summary.get("notes") or [],
        "screening_messages": summary.get("screening_messages") or [],
    }


def _build_operation_report(ann: Any) -> dict[str, Any]:
    rep_day = _representative_operation_day(ann)
    hourly_series = []
    for d in range(365):
        for h in range(24):
            hourly_series.append(
                {
                    "day_index": d + 1,
                    "hour": h,
                    "charge_kw": float(ann.exec_charge_kw[d, h]),
                    "discharge_kw": float(ann.exec_discharge_kw[d, h]),
                    "grid_exchange_kw": float(ann.grid_exchange_kw[d, h]),
                    "soc_open": float(ann.soc_hourly_path[d, h]),
                    "soc_close": float(ann.soc_hourly_path[d, h + 1]),
                    "tariff_yuan_per_kwh": float(ann.tariff_yuan_per_kwh[d, h]),
                }
            )
    return {
        "report_type": "operation",
        "evaluation_mode": ann.evaluation_mode,
        "annual_metrics": {
            "equivalent_full_cycles": float(ann.annual_equivalent_full_cycles),
            "battery_throughput_kwh": float(ann.annual_battery_throughput_kwh),
            "avg_daily_charge_kwh": float(ann.exec_charge_kw.sum() / 365.0),
            "avg_daily_discharge_kwh": float(ann.exec_discharge_kw.sum() / 365.0),
            "soc_start": float(ann.soc_daily_open[0]),
            "soc_end": float(ann.soc_daily_close[-1]),
        },
        "representative_day_profile": {
            "day_index": rep_day + 1,
            "charge_kw": ann.exec_charge_kw[rep_day].tolist(),
            "discharge_kw": ann.exec_discharge_kw[rep_day].tolist(),
            "soc": ann.soc_hourly_path[rep_day].tolist(),
            "grid_exchange_kw": ann.grid_exchange_kw[rep_day].tolist(),
            "tariff_yuan_per_kwh": ann.tariff_yuan_per_kwh[rep_day].tolist(),
        },
        "hourly_series": hourly_series,
    }


def _sum_attr_array(obj: Any, name: str) -> float | None:
    if obj is None or not hasattr(obj, name):
        return None
    value = getattr(obj, name)
    try:
        if hasattr(value, "sum"):
            return float(value.sum())
        return float(sum(float(x) for x in value))
    except Exception:
        return None


def _ledger_item(
    *,
    name: str,
    category: str,
    amount_yuan: float,
    quantity: float | None,
    quantity_unit: str,
    unit_price: float | None,
    unit_price_unit: str,
    formula: str,
    source: str,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "amount_yuan": float(amount_yuan),
        "quantity": None if quantity is None else float(quantity),
        "quantity_unit": quantity_unit,
        "unit_price": None if unit_price is None else float(unit_price),
        "unit_price_unit": unit_price_unit,
        "formula": formula,
        "source": source,
        "notes": notes,
    }


def _build_financial_audit_ledger(summary: dict[str, Any], ann_summary: dict[str, Any], fin: Any, ann: Any | None) -> dict[str, Any]:
    audit = getattr(fin, "annual_revenue_audit", None)
    audit_meta = getattr(audit, "metadata", {}) if audit is not None else {}
    if not isinstance(audit_meta, dict):
        audit_meta = {}

    rated_power = _safe_float(summary.get("rated_power_kw"))
    rated_energy = _safe_float(summary.get("rated_energy_kwh"))
    throughput = _safe_float(ann_summary.get("annual_battery_throughput_kwh"))
    charge_kwh = _sum_attr_array(ann, "exec_charge_kw")
    discharge_kwh = _sum_attr_array(ann, "exec_discharge_kw")
    service_kw_h = _sum_attr_array(ann, "exec_service_kw")

    items: list[dict[str, Any]] = []

    arbitrage_amount = _safe_float(ann_summary.get("annual_arbitrage_revenue_yuan"))
    items.append(
        _ledger_item(
            name="峰谷套利收益",
            category="revenue",
            amount_yuan=arbitrage_amount,
            quantity=discharge_kwh,
            quantity_unit="kWh discharged",
            unit_price=arbitrage_amount / discharge_kwh if discharge_kwh and abs(discharge_kwh) > 1e-9 else None,
            unit_price_unit="yuan/kWh discharged",
            formula="Σ_t 电价_t × (放电量_t - 充电量_t)",
            source="AnnualOperationResult.tariff_yuan_per_kwh / exec_charge_kw / exec_discharge_kw",
            notes="数量按年放电电量展示；单价为便于审计的等效套利收益单价，真实金额仍由逐时电价与充放电量求和得到。",
        )
    )

    demand_price = _safe_float(audit_meta.get("demand_charge_yuan_per_kw_month_effective"))
    demand_quantity = _safe_float(audit_meta.get("annual_demand_saving_kw_month_effective"))
    items.append(
        _ledger_item(
            name="需量收益",
            category="revenue",
            amount_yuan=_safe_float(summary.get("annual_demand_saving_yuan")),
            quantity=demand_quantity,
            quantity_unit="kW·month",
            unit_price=demand_price if demand_price > 0 else None,
            unit_price_unit="yuan/kW·month",
            formula="Σ_month max(0, 储前月最大需量 - 储后月最大需量) × 需量单价",
            source=str(audit_meta.get("demand_saving_source", "annual_result")),
        )
    )

    service_capacity = _safe_float(ann_summary.get("annual_service_capacity_revenue_yuan"))
    items.append(
        _ledger_item(
            name="辅助服务容量收益",
            category="revenue",
            amount_yuan=service_capacity,
            quantity=service_kw_h,
            quantity_unit="kW·h",
            unit_price=service_capacity / service_kw_h if service_kw_h and service_kw_h > 1e-9 else None,
            unit_price_unit="yuan/kW·h",
            formula="Σ_t 辅助服务容量价格_t × 服务预留功率_t",
            source="RollingDispatchResult.service_capacity_revenue_yuan_by_hour",
        )
    )

    service_delivery = _safe_float(ann_summary.get("annual_service_delivery_revenue_yuan"))
    items.append(
        _ledger_item(
            name="辅助服务履约收益",
            category="revenue",
            amount_yuan=service_delivery,
            quantity=service_kw_h,
            quantity_unit="kW·h",
            unit_price=service_delivery / service_kw_h if service_kw_h and service_kw_h > 1e-9 else None,
            unit_price_unit="yuan/kW·h",
            formula="Σ_t 辅助服务履约价格_t × 触发系数_t × 服务功率_t",
            source="RollingDispatchResult.service_delivery_revenue_yuan_by_hour",
        )
    )

    service_penalty = _safe_float(ann_summary.get("annual_service_penalty_yuan"))
    items.append(
        _ledger_item(
            name="辅助服务罚金",
            category="cost",
            amount_yuan=service_penalty,
            quantity=None,
            quantity_unit="",
            unit_price=None,
            unit_price_unit="",
            formula="Σ_t 罚金价格_t × 服务缺额_t",
            source="RollingDispatchResult.service_penalty_yuan_by_hour",
        )
    )

    capacity_kw = _safe_float(audit_meta.get("capacity_revenue_kw_effective"))
    capacity_days = _safe_float(audit_meta.get("capacity_revenue_eligible_days_effective"))
    capacity_price = _safe_float(audit_meta.get("capacity_service_price_yuan_per_kw_day_effective"))
    items.append(
        _ledger_item(
            name="容量收益",
            category="revenue",
            amount_yuan=_safe_float(summary.get("annual_capacity_revenue_yuan")),
            quantity=capacity_kw * capacity_days if capacity_kw and capacity_days else None,
            quantity_unit="kW·day",
            unit_price=capacity_price if capacity_price > 0 else None,
            unit_price_unit="yuan/kW·day",
            formula="有效容量功率 × 可计收益天数 × 容量收益单价",
            source="AnnualRevenueAuditor.capacity_meta",
        )
    )

    loss_quantity = _safe_float(audit_meta.get("annual_loss_reduction_kwh"))
    loss_price = _safe_float(audit_meta.get("network_loss_price_yuan_per_kwh_effective"))
    items.append(
        _ledger_item(
            name="降损收益",
            category="revenue",
            amount_yuan=_safe_float(summary.get("annual_loss_reduction_revenue_yuan")),
            quantity=loss_quantity,
            quantity_unit="kWh",
            unit_price=loss_price if loss_price > 0 else None,
            unit_price_unit="yuan/kWh",
            formula="储前后 OpenDSS 网损差额电量 × 降损电价",
            source=str(audit_meta.get("network_loss_quantity_source_effective", "unknown")),
        )
    )

    fixed_om_price = _safe_float(audit_meta.get("annual_fixed_om_yuan_per_kw_year"))
    variable_om_price = _safe_float(audit_meta.get("annual_variable_om_yuan_per_kwh"))
    items.append(
        _ledger_item(
            name="固定运维成本",
            category="cost",
            amount_yuan=rated_power * fixed_om_price,
            quantity=rated_power,
            quantity_unit="kW",
            unit_price=fixed_om_price,
            unit_price_unit="yuan/kW·year",
            formula="额定功率 × 固定运维单价",
            source="AnnualRevenueAuditor.metadata",
        )
    )
    items.append(
        _ledger_item(
            name="可变运维成本",
            category="cost",
            amount_yuan=throughput * variable_om_price,
            quantity=throughput,
            quantity_unit="kWh throughput",
            unit_price=variable_om_price,
            unit_price_unit="yuan/kWh",
            formula="年吞吐电量 × 可变运维单价",
            source="AnnualRevenueAuditor.metadata",
        )
    )

    degradation_amount = _safe_float(summary.get("annual_degradation_cost_yuan"))
    items.append(
        _ledger_item(
            name="退化成本",
            category="cost",
            amount_yuan=degradation_amount,
            quantity=throughput,
            quantity_unit="kWh throughput",
            unit_price=degradation_amount / throughput if throughput and throughput > 1e-9 else None,
            unit_price_unit="yuan/kWh throughput",
            formula="Σ_t 退化单价 × (充电量_t + 放电量_t + 服务折算电量_t)",
            source="RollingDispatchResult.degradation_cost_yuan_by_hour",
        )
    )

    gross_capex = _safe_float(summary.get("gross_initial_investment_yuan", summary.get("initial_investment_yuan")))
    subsidy = _safe_float(summary.get("government_subsidy_yuan"))
    subsidy_rate = _safe_float(summary.get("government_subsidy_rate_on_capex_effective"))
    subsidy_kwh = _safe_float(summary.get("government_subsidy_yuan_per_kwh_effective"))
    subsidy_kw = _safe_float(summary.get("government_subsidy_yuan_per_kw_effective"))
    subsidy_cap = _safe_float(summary.get("government_subsidy_cap_yuan_effective"))
    items.append(
        _ledger_item(
            name="政府补贴",
            category="subsidy",
            amount_yuan=subsidy,
            quantity=None,
            quantity_unit="",
            unit_price=None,
            unit_price_unit="",
            formula=(
                "min(初始投资×补贴比例 + 容量×元/kWh + 功率×元/kW, 补贴上限)；"
                f"当前参数：投资 {gross_capex:.2f} 元、比例 {subsidy_rate:.4f}、容量单价 {subsidy_kwh:.4f}、"
                f"功率单价 {subsidy_kw:.4f}、上限 {subsidy_cap:.2f} 元"
            ),
            source="LifecycleFinancialEvaluator.metadata",
        )
    )

    replacement_annual = _safe_float(summary.get("annual_replacement_equivalent_cost_yuan"))
    items.append(
        _ledger_item(
            name="更换成本年化",
            category="cost",
            amount_yuan=replacement_annual,
            quantity=_safe_float(summary.get("total_replacement_cost_yuan")),
            quantity_unit="yuan lifecycle",
            unit_price=None,
            unit_price_unit="",
            formula="生命周期总更换成本 / 项目寿命年数",
            source="LifecycleCashflowTable.replacement_cost_yuan",
        )
    )

    return {
        "currency": "CNY",
        "items": items,
        "notes": [
            "功率类数量按 1 小时时步折算为 kW·h；若价格为时变价格，unit_price 为按年度金额反推的等效均价。",
            "峰谷套利收益由逐时电价和逐时充放电直接求和，不是固定单价项。",
        ],
    }


def _build_financial_report(fin: Any, ann: Any | None) -> dict[str, Any]:
    summary = fin.summary_dict() if hasattr(fin, "summary_dict") else {}
    ann_summary = ann.summary_dict() if ann is not None and hasattr(ann, "summary_dict") else {}
    service_net = (
        _safe_float(summary.get("annual_auxiliary_service_revenue_yuan"))
        or (
            _safe_float(ann_summary.get("annual_service_capacity_revenue_yuan"))
            + _safe_float(ann_summary.get("annual_service_delivery_revenue_yuan"))
            - _safe_float(ann_summary.get("annual_service_penalty_yuan"))
        )
    )
    return {
        "report_type": "financial",
        "core_metrics": {
            "npv_yuan": _safe_float(summary.get("npv_yuan")),
            "irr": _to_float(summary.get("irr")),
            "simple_payback_years": _to_float(summary.get("simple_payback_years")),
            "discounted_payback_years": _to_float(summary.get("discounted_payback_years")),
            "initial_investment_yuan": _safe_float(summary.get("initial_investment_yuan")),
            "initial_net_investment_yuan": _safe_float(summary.get("initial_net_investment_yuan")),
        },
        "annual_revenue_breakdown_yuan": {
            "arbitrage": _safe_float(ann_summary.get("annual_arbitrage_revenue_yuan")),
            "demand_saving": _safe_float(summary.get("annual_demand_saving_yuan")),
            "auxiliary_service_net": service_net,
            "capacity": _safe_float(summary.get("annual_capacity_revenue_yuan")),
            "loss_reduction": _safe_float(summary.get("annual_loss_reduction_revenue_yuan")),
            "government_subsidy": _safe_float(summary.get("government_subsidy_yuan")),
        },
        "annual_cost_breakdown_yuan": {
            "degradation": _safe_float(summary.get("annual_degradation_cost_yuan")),
            "om": _safe_float(summary.get("annual_om_cost_yuan")),
            "replacement_equivalent": _safe_float(summary.get("annual_replacement_equivalent_cost_yuan")),
            "transformer_penalty": _safe_float(ann_summary.get("annual_transformer_penalty_yuan")),
            "voltage_penalty": _safe_float(ann_summary.get("annual_voltage_penalty_yuan")),
        },
        "annual_audit_ledger": _build_financial_audit_ledger(summary, ann_summary, fin, ann),
        "raw_summary": summary,
    }


def _risk_classification(
    baseline_hours: float,
    with_storage_hours: float,
    baseline_max_violation: float,
    with_storage_max_violation: float,
) -> str:
    eps = 1e-9
    if baseline_hours <= eps and with_storage_hours <= eps and with_storage_max_violation <= eps:
        return "normal"
    if baseline_hours <= eps and with_storage_hours > eps:
        return "storage_induced"
    if with_storage_hours <= eps and baseline_hours > eps:
        return "cleared_by_storage"
    if with_storage_hours > baseline_hours + eps or with_storage_max_violation > baseline_max_violation + eps:
        return "worsened_by_storage"
    if with_storage_hours < baseline_hours - eps or with_storage_max_violation < baseline_max_violation - eps:
        return "improved_by_storage"
    return "existing_background"


def _top_voltage_risks(bus_trace_rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    by_bus: dict[str, dict[str, Any]] = {}
    for row in bus_trace_rows:
        bus = str(row.get("bus") or "").strip()
        if not bus:
            continue
        item = by_bus.setdefault(
            bus,
            {
                "bus": bus,
                "baseline_violation_hours": 0.0,
                "with_storage_violation_hours": 0.0,
                "max_baseline_violation_pu": 0.0,
                "max_with_storage_violation_pu": 0.0,
                "max_storage_increment_pu": 0.0,
                "min_baseline_voltage_pu": None,
                "max_baseline_voltage_pu": None,
                "min_with_storage_voltage_pu": None,
                "max_with_storage_voltage_pu": None,
            },
        )
        baseline_violation = _voltage_violation_pu(row.get("baseline_voltage_pu_min"), row.get("baseline_voltage_pu_max"))
        with_storage_violation = _voltage_violation_pu(row.get("voltage_pu_min"), row.get("voltage_pu_max"))
        storage_increment = max(0.0, with_storage_violation - baseline_violation)
        if baseline_violation > 1e-9:
            item["baseline_violation_hours"] += 1.0
        if with_storage_violation > 1e-9:
            item["with_storage_violation_hours"] += 1.0
        item["max_baseline_violation_pu"] = max(item["max_baseline_violation_pu"], baseline_violation)
        item["max_with_storage_violation_pu"] = max(item["max_with_storage_violation_pu"], with_storage_violation)
        item["max_storage_increment_pu"] = max(item["max_storage_increment_pu"], storage_increment)

        for source_key, target_key, reducer in (
            ("baseline_voltage_pu_min", "min_baseline_voltage_pu", min),
            ("baseline_voltage_pu_max", "max_baseline_voltage_pu", max),
            ("voltage_pu_min", "min_with_storage_voltage_pu", min),
            ("voltage_pu_max", "max_with_storage_voltage_pu", max),
        ):
            value = _to_float(row.get(source_key))
            if value is None:
                continue
            item[target_key] = value if item[target_key] is None else reducer(item[target_key], value)

    risks = []
    for item in by_bus.values():
        item["classification"] = _risk_classification(
            item["baseline_violation_hours"],
            item["with_storage_violation_hours"],
            item["max_baseline_violation_pu"],
            item["max_with_storage_violation_pu"],
        )
        item["delta_violation_hours"] = item["with_storage_violation_hours"] - item["baseline_violation_hours"]
        item["delta_max_violation_pu"] = item["max_with_storage_violation_pu"] - item["max_baseline_violation_pu"]
        if item["classification"] != "normal":
            risks.append(item)

    risks.sort(
        key=lambda item: (
            item["with_storage_violation_hours"],
            item["max_with_storage_violation_pu"],
            item["max_storage_increment_pu"],
        ),
        reverse=True,
    )
    return risks[:limit]


def _top_line_risks(line_trace_rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    by_line: dict[str, dict[str, Any]] = {}
    for row in line_trace_rows:
        line = str(row.get("line") or "").strip()
        if not line:
            continue
        item = by_line.setdefault(
            line,
            {
                "line": line,
                "bus1": row.get("bus1"),
                "bus2": row.get("bus2"),
                "normamps": row.get("normamps"),
                "emergamps": row.get("emergamps"),
                "baseline_overload_hours": 0.0,
                "with_storage_overload_hours": 0.0,
                "max_baseline_loading_pct": 0.0,
                "max_with_storage_loading_pct": 0.0,
                "max_baseline_overload_pct": 0.0,
                "max_with_storage_overload_pct": 0.0,
                "max_storage_increment_pct": 0.0,
            },
        )
        baseline_loading = _safe_float(row.get("baseline_loading_pct"))
        with_storage_loading = _safe_float(row.get("loading_pct"))
        baseline_overload = max(0.0, baseline_loading - 100.0)
        with_storage_overload = max(0.0, with_storage_loading - 100.0)
        if baseline_overload > 1e-9:
            item["baseline_overload_hours"] += 1.0
        if with_storage_overload > 1e-9:
            item["with_storage_overload_hours"] += 1.0
        item["max_baseline_loading_pct"] = max(item["max_baseline_loading_pct"], baseline_loading)
        item["max_with_storage_loading_pct"] = max(item["max_with_storage_loading_pct"], with_storage_loading)
        item["max_baseline_overload_pct"] = max(item["max_baseline_overload_pct"], baseline_overload)
        item["max_with_storage_overload_pct"] = max(item["max_with_storage_overload_pct"], with_storage_overload)
        item["max_storage_increment_pct"] = max(item["max_storage_increment_pct"], max(0.0, with_storage_overload - baseline_overload))

    risks = []
    for item in by_line.values():
        item["classification"] = _risk_classification(
            item["baseline_overload_hours"],
            item["with_storage_overload_hours"],
            item["max_baseline_overload_pct"],
            item["max_with_storage_overload_pct"],
        )
        item["delta_overload_hours"] = item["with_storage_overload_hours"] - item["baseline_overload_hours"]
        item["delta_max_overload_pct"] = item["max_with_storage_overload_pct"] - item["max_baseline_overload_pct"]
        if item["classification"] != "normal":
            risks.append(item)

    risks.sort(
        key=lambda item: (
            item["with_storage_overload_hours"],
            item["max_with_storage_overload_pct"],
            item["max_storage_increment_pct"],
        ),
        reverse=True,
    )
    return risks[:limit]


def _risk_classification_counts(risks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in risks:
        key = str(item.get("classification") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _network_risk_classification_summary(risk_details: dict[str, Any]) -> dict[str, Any]:
    classes = ["existing_background", "storage_induced", "worsened_by_storage", "improved_by_storage", "cleared_by_storage", "normal"]
    summary = {
        key: {"total": 0, "voltage": 0, "line": 0, "transformer": 0}
        for key in classes
    }
    for source_key, bucket in [("voltage_classification_counts", "voltage"), ("line_classification_counts", "line")]:
        counts = risk_details.get(source_key) if isinstance(risk_details.get(source_key), dict) else {}
        for key, value in counts.items():
            class_key = str(key or "normal")
            summary.setdefault(class_key, {"total": 0, "voltage": 0, "line": 0, "transformer": 0})
            count = int(value or 0)
            summary[class_key][bucket] += count
            summary[class_key]["total"] += count
    transformer = risk_details.get("transformer") if isinstance(risk_details.get("transformer"), dict) else {}
    transformer_class = str(transformer.get("classification") or "normal")
    if transformer_class:
        summary.setdefault(transformer_class, {"total": 0, "voltage": 0, "line": 0, "transformer": 0})
        summary[transformer_class]["transformer"] += 1
        summary[transformer_class]["total"] += 1
    return {
        "items": [
            {"classification": key, **value}
            for key, value in summary.items()
            if value["total"] > 0 or key in classes
        ],
        "total_risks": sum(value["total"] for value in summary.values()),
    }


def _transformer_top_risks(report: dict[str, Any], risk_details: dict[str, Any]) -> list[dict[str, Any]]:
    transformer = risk_details.get("transformer") if isinstance(risk_details.get("transformer"), dict) else {}
    if not transformer:
        return []
    baseline_hours = _safe_float(transformer.get("baseline_overload_hours"))
    with_storage_hours = _safe_float(transformer.get("with_storage_overload_hours"))
    baseline = report.get("baseline") if isinstance(report.get("baseline"), dict) else {}
    with_storage = report.get("with_storage") if isinstance(report.get("with_storage"), dict) else {}
    return [
        {
            "transformer": transformer.get("transformer") or "目标上级配变",
            "classification": transformer.get("classification") or "normal",
            "baseline_overload_hours": baseline_hours,
            "with_storage_overload_hours": with_storage_hours,
            "overload_hour_delta": with_storage_hours - baseline_hours,
            "max_baseline_loading_pct": baseline.get("max_transformer_loading_pct"),
            "max_with_storage_loading_pct": with_storage.get("max_transformer_loading_pct"),
            "source": "network_impact_report.risk_details.transformer",
        }
    ]


def _delta_text(delta: float, metric_name: str) -> str:
    if delta > 1e-6:
        return f"{metric_name}改善，储后指标较储前降低。"
    if delta < -1e-6:
        return f"{metric_name}恶化，储后指标较储前升高。"
    return f"{metric_name}基本持平。"


def _target_area_conclusion(report: dict[str, Any]) -> dict[str, Any]:
    target = report.get("target_connection") if isinstance(report.get("target_connection"), dict) else {}
    delta = target.get("delta") if isinstance(target.get("delta"), dict) else {}
    safety_delta = _safe_float(delta.get("safety_violation_hours"))
    voltage_delta = _safe_float(delta.get("max_voltage_violation_pu"))
    line_delta = _safe_float(delta.get("max_line_loading_pct"))
    if safety_delta < -1e-6 or voltage_delta < -1e-6 or line_delta < -1e-6:
        status = "worsened"
        conclusion = "该储能方案加剧目标接入区域风险，需重点复核目标节点电压、接入线路和上游配变。"
    elif safety_delta > 1e-6 or voltage_delta > 1e-6 or line_delta > 1e-6:
        status = "improved"
        conclusion = "该储能方案未加剧目标接入区域风险，并对部分安全越限指标有改善。"
    else:
        status = "neutral"
        conclusion = "该储能方案对目标接入区域风险影响不明显，主要风险来自原网背景或数据缺口。"
    return {
        "status": status,
        "conclusion": conclusion,
        "target_node": target.get("target_node"),
        "target_transformer": target.get("target_transformer"),
        "access_line": target.get("access_line"),
        "upstream_feeder": target.get("upstream_feeder"),
        "metrics": {
            "safety_violation_hours_delta": safety_delta,
            "max_voltage_violation_pu_delta": voltage_delta,
            "max_line_loading_pct_delta": line_delta,
        },
    }


def _network_attribution_summary(report: dict[str, Any]) -> dict[str, Any]:
    delta = report.get("delta") if isinstance(report.get("delta"), dict) else {}
    target = report.get("target_connection") if isinstance(report.get("target_connection"), dict) else {}
    target_delta = target.get("delta") if isinstance(target.get("delta"), dict) else {}
    safety_delta = _safe_float(delta.get("safety_violation_hours"))
    loss_delta = _safe_float(delta.get("loss_reduction_kwh"))
    voltage_delta = _safe_float(delta.get("max_voltage_violation_pu"))
    line_delta = _safe_float(delta.get("max_line_loading_pct"))
    target_safety_delta = _safe_float(target_delta.get("safety_violation_hours"))
    return {
        "voltage": _delta_text(voltage_delta, "电压越限幅度"),
        "line_loading": _delta_text(line_delta, "线路最大负载率"),
        "target_area": _delta_text(target_safety_delta, "目标区域安全越限小时"),
        "losses": _delta_text(loss_delta, "网损"),
        "primary_drivers": [
            text
            for text in [
                "削峰降低安全越限小时" if safety_delta > 1e-6 else "",
                "局部反送或储能充放电加重越限" if safety_delta < -1e-6 else "",
                "网损下降贡献经济收益" if loss_delta > 1e-6 else "",
                "网损上升抵消部分收益" if loss_delta < -1e-6 else "",
            ]
            if text
        ],
    }


def _build_network_impact_report(
    ann: Any,
    hourly_network_trace: dict[tuple[int, int], dict[str, Any]],
    bus_trace_rows: list[dict[str, Any]] | None = None,
    line_trace_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ann_summary = ann.summary_dict()
    trace_rows = list(hourly_network_trace.values())
    voltage_risks = _top_voltage_risks(bus_trace_rows or [])
    line_risks = _top_line_risks(line_trace_rows or [])
    baseline = {
        "voltage_violation_hours": _safe_float(ann_summary.get("baseline_hours_with_voltage_violation")),
        "line_overload_hours": _safe_float(ann_summary.get("baseline_hours_with_line_overload")),
        "transformer_overload_hours": _safe_float(ann_summary.get("baseline_transformer_violation_hours")),
        "max_voltage_violation_pu": _safe_float(ann_summary.get("max_baseline_voltage_violation_pu")),
        "max_line_loading_pct": _safe_float(ann_summary.get("max_baseline_line_loading_pct")),
        "losses_kwh": _safe_sum(trace_rows, "opendss_loss_baseline_kw"),
    }
    with_storage = {
        "voltage_violation_hours": _safe_float(ann_summary.get("hours_with_voltage_violation")),
        "line_overload_hours": _safe_float(ann_summary.get("hours_with_line_overload")),
        "transformer_overload_hours": _safe_float(ann_summary.get("transformer_violation_hours")),
        "max_voltage_violation_pu": _safe_float(ann_summary.get("max_voltage_violation_pu")),
        "max_line_loading_pct": _safe_float(ann_summary.get("max_line_loading_pct")),
        "losses_kwh": _safe_sum(trace_rows, "opendss_loss_with_storage_kw"),
    }
    target_baseline = {
        "voltage_violation_hours": _safe_float(ann_summary.get("baseline_target_hours_with_voltage_violation")),
        "line_overload_hours": _safe_float(ann_summary.get("baseline_target_hours_with_line_overload")),
        "transformer_overload_hours": _safe_float(ann_summary.get("baseline_transformer_violation_hours")),
        "max_voltage_violation_pu": _safe_float(ann_summary.get("max_baseline_target_voltage_violation_pu")),
        "max_line_loading_pct": _safe_float(ann_summary.get("max_baseline_target_line_loading_pct")),
    }
    target_with_storage = {
        "voltage_violation_hours": _safe_float(ann_summary.get("target_hours_with_voltage_violation")),
        "line_overload_hours": _safe_float(ann_summary.get("target_hours_with_line_overload")),
        "transformer_overload_hours": _safe_float(ann_summary.get("transformer_violation_hours")),
        "max_voltage_violation_pu": _safe_float(ann_summary.get("max_target_voltage_violation_pu")),
        "max_line_loading_pct": _safe_float(ann_summary.get("max_target_line_loading_pct")),
    }
    baseline_total = sum(
        baseline[key]
        for key in ("voltage_violation_hours", "line_overload_hours", "transformer_overload_hours")
    )
    storage_total = sum(
        with_storage[key]
        for key in ("voltage_violation_hours", "line_overload_hours", "transformer_overload_hours")
    )
    target_baseline_total = sum(
        target_baseline[key]
        for key in ("voltage_violation_hours", "line_overload_hours", "transformer_overload_hours")
    )
    target_storage_total = sum(
        target_with_storage[key]
        for key in ("voltage_violation_hours", "line_overload_hours", "transformer_overload_hours")
    )
    risk_details = {
        "voltage_top_risks": voltage_risks,
        "line_top_risks": line_risks,
        "voltage_classification_counts": _risk_classification_counts(voltage_risks),
        "line_classification_counts": _risk_classification_counts(line_risks),
        "transformer": {
            "baseline_overload_hours": baseline["transformer_overload_hours"],
            "with_storage_overload_hours": with_storage["transformer_overload_hours"],
            "classification": _risk_classification(
                baseline["transformer_overload_hours"],
                with_storage["transformer_overload_hours"],
                _safe_float(ann_summary.get("max_transformer_slack_kw")),
                _safe_float(ann_summary.get("max_transformer_slack_kw")),
            ),
        },
        "classification_meaning": {
            "storage_induced": "储前无越限，储后出现越限。",
            "worsened_by_storage": "储前已有风险，储后越限小时数或最大越限幅度增加。",
            "improved_by_storage": "储后越限小时数或最大越限幅度降低。",
            "cleared_by_storage": "储前有越限，储后清除。",
            "existing_background": "储前已有风险，储后基本未改变。",
        },
    }
    report = {
        "report_type": "network_impact",
        "baseline": baseline,
        "with_storage": with_storage,
        "target_connection": {
            "baseline": target_baseline,
            "with_storage": target_with_storage,
            "delta": {
                "safety_violation_hours": target_baseline_total - target_storage_total,
                "max_voltage_violation_pu": (
                    target_baseline["max_voltage_violation_pu"] - target_with_storage["max_voltage_violation_pu"]
                ),
                "max_line_loading_pct": (
                    target_baseline["max_line_loading_pct"] - target_with_storage["max_line_loading_pct"]
                ),
            },
        },
        "risk_details": risk_details,
        "delta": {
            "safety_violation_hours": baseline_total - storage_total,
            "loss_reduction_kwh": _safe_sum(trace_rows, "opendss_loss_reduction_kwh"),
            "max_voltage_violation_pu": baseline["max_voltage_violation_pu"] - with_storage["max_voltage_violation_pu"],
            "max_line_loading_pct": baseline["max_line_loading_pct"] - with_storage["max_line_loading_pct"],
        },
        "data_quality": {
            "opendss_trace_hours": len(trace_rows),
            "has_opendss_loss": any(row.get("opendss_loss_baseline_kw") is not None for row in trace_rows),
            "opendss_convergence_known_hours": sum(1 for row in trace_rows if row.get("opendss_solve_converged") is not None),
            "opendss_not_converged_hours": sum(1 for row in trace_rows if row.get("opendss_solve_converged") is False),
        },
    }
    transformer_top_risks = _transformer_top_risks(report, risk_details)
    risk_details["transformer_top_risks"] = transformer_top_risks
    report["risk_classification_summary"] = _network_risk_classification_summary(risk_details)
    report["target_area_conclusion"] = _target_area_conclusion(report)
    report["transformer_top_risks"] = transformer_top_risks
    report["attribution_summary"] = _network_attribution_summary(report)
    return report


def _add_health_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    reason: str | None = None,
    impact: str | None = None,
    suggestion: str | None = None,
    related_section: str | None = None,
) -> None:
    defaults = _health_issue_defaults(code, message)
    level = "critical" if severity in {"error", "critical", "failed"} else "warning"
    issues.append(
        {
            "severity": severity,
            "level": level,
            "code": code,
            "message": message,
            "reason": reason or defaults["reason"],
            "impact": impact or defaults["impact"],
            "suggestion": suggestion or defaults["suggestion"],
            "related_section": related_section or defaults["related_section"],
            "details": details or {},
        }
    )


def _health_issue_defaults(code: str, message: str) -> dict[str, str]:
    text = f"{code} {message}".lower()
    if "feasib" in text or "infeasible" in text:
        return {
            "reason": "候选方案可行性或最优方案可行性异常。",
            "impact": "储能配置方案可能不是严格可执行方案，经济性和运行曲线可信度下降。",
            "suggestion": "优先查看可行性诊断、约束罚分和候选方案状态，必要时收紧搜索空间后重跑。",
            "related_section": "feasibility",
        }
    if "soc" in text:
        return {
            "reason": "SOC 越界或能量守恒检查异常。",
            "impact": "年运行情况中的充放电轨迹和循环统计可能失真。",
            "suggestion": "检查储能容量、效率、初始 SOC、SOC 上下限和逐时调度约束。",
            "related_section": "operation",
        }
    if "opendss" in text or "network" in text or "voltage" in text or "line" in text:
        return {
            "reason": "OpenDSS 潮流、配网越限或网络约束检查异常。",
            "impact": "配网承载力变化结论可能不完整，需关注电压、线路和配变风险。",
            "suggestion": "检查 DSS 编译、目标接入母线、线路额定电流和潮流收敛小时。",
            "related_section": "network_impact",
        }
    if "economic" in text or "economics" in text or "npv" in text or "irr" in text:
        return {
            "reason": "经济性核心字段缺失、非有限值或异常值。",
            "impact": "经济性结论和审计账本不能直接作为可信收益判断。",
            "suggestion": "检查电价、收益开关、成本参数、退化和更换成本输入。",
            "related_section": "financial",
        }
    return {
        "reason": message or "健康检查发现异常。",
        "impact": "结果可信性需要结合相关模块进一步核对。",
        "suggestion": "查看 issue details 和关联结果文件，必要时重新运行求解。",
        "related_section": "run_health",
    }


def _health_status(issues: list[dict[str, Any]]) -> str:
    levels = {str(item.get("level") or item.get("severity") or "") for item in issues}
    if "critical" in levels or "error" in levels:
        return "critical"
    if "warning" in levels:
        return "warning"
    return "passed"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "reshape"):
        try:
            return list(value.reshape(-1))
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _finite_values(value: Any) -> list[float]:
    values: list[float] = []
    for item in _as_list(value):
        parsed = _to_float(item)
        if parsed is not None and math.isfinite(parsed):
            values.append(float(parsed))
    return values


def _result_summary(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if hasattr(result, "summary_dict"):
        try:
            return result.summary_dict()
        except Exception:
            return {}
    return {}


def _check_feasibility_health(run_result: LemmingOptimizationRunResult, issues: list[dict[str, Any]]) -> dict[str, Any]:
    population = list(getattr(run_result, "population_results", None) or [])
    archive = list(getattr(run_result, "archive_results", None) or [])

    def counts(results: list[Any]) -> dict[str, Any]:
        total = len(results)
        feasible = sum(1 for item in results if bool(getattr(item, "feasible", False)))
        valid = sum(1 for item in results if bool(getattr(item, "is_valid", False)))
        infeasible_ratio = (1.0 - feasible / total) if total else None
        return {
            "total": total,
            "valid_count": valid,
            "feasible_count": feasible,
            "infeasible_count": total - feasible,
            "infeasible_ratio": infeasible_ratio,
        }

    pop = counts(population)
    arc = counts(archive)
    best = getattr(run_result, "best_result", None)
    best_feasible = bool(getattr(best, "feasible", False)) if best is not None else False

    if pop["total"] and pop["feasible_count"] == 0:
        _add_health_issue(issues, "error", "no_feasible_solution_in_final_population", "最终种群没有可行解。", pop)
    elif pop["infeasible_ratio"] is not None and pop["infeasible_ratio"] >= 0.70:
        _add_health_issue(issues, "warning", "high_infeasible_solution_ratio", "最终种群不可行解占比偏高。", pop)

    if best is None:
        _add_health_issue(issues, "error", "missing_best_result", "本次运行没有选出最优方案。")
    elif not best_feasible:
        _add_health_issue(issues, "warning", "best_result_not_feasible", "当前最优折中解仍存在约束违背。", _result_summary(best))

    return {
        "population": pop,
        "archive": arc,
        "best_feasible": best_feasible,
    }


def _check_soc_health(ann: Any, issues: list[dict[str, Any]]) -> dict[str, Any]:
    if ann is None:
        _add_health_issue(issues, "warning", "missing_annual_operation_result", "缺少年度运行结果，无法检查 SOC。")
        return {"available": False}

    values = _finite_values(getattr(ann, "soc_hourly_path", None))
    expected_count = 365 * 25
    nonfinite_count = max(0, expected_count - len(values))
    result: dict[str, Any] = {
        "available": True,
        "finite_count": len(values),
        "expected_count": expected_count,
        "nonfinite_count": nonfinite_count,
        "min_soc": min(values) if values else None,
        "max_soc": max(values) if values else None,
    }

    if nonfinite_count:
        _add_health_issue(issues, "error", "soc_nonfinite_values", "SOC 序列存在 NaN/None/非有限值。", result)

    if values:
        low_count = sum(1 for value in values if value < -1e-6)
        high_count = sum(1 for value in values if value > 1.0 + 1e-6)
        result["below_zero_count"] = low_count
        result["above_one_count"] = high_count
        if low_count or high_count:
            _add_health_issue(issues, "error", "soc_out_of_bounds", "SOC 存在越界。", result)

    try:
        open_values = _finite_values(getattr(ann, "soc_daily_open", None))
        close_values = _finite_values(getattr(ann, "soc_daily_close", None))
        if len(open_values) >= 365 and len(close_values) >= 365:
            gaps = [abs(open_values[i] - close_values[i - 1]) for i in range(1, 365)]
            max_gap = max(gaps) if gaps else 0.0
            result["max_day_continuity_gap"] = float(max_gap)
            if str(getattr(ann, "evaluation_mode", "")).lower() in {"full_year", "full_recheck"} and max_gap > 1e-4:
                _add_health_issue(
                    issues,
                    "warning",
                    "soc_daily_continuity_gap",
                    "全年逐日 SOC 存在日间连续性偏差。",
                    {"max_day_continuity_gap": max_gap},
                )
    except Exception:
        result["continuity_check_error"] = True

    daily_execs = list(getattr(ann, "daily_exec_objects", None) or [])
    balance_residuals = [
        _safe_float(getattr(item, "metadata", {}).get("soc_energy_balance_max_abs"))
        for item in daily_execs
        if isinstance(getattr(item, "metadata", None), dict)
    ]
    if balance_residuals:
        max_residual = max(balance_residuals)
        result["max_soc_energy_balance_residual"] = float(max_residual)
        if max_residual > 1e-2:
            _add_health_issue(
                issues,
                "error",
                "soc_energy_balance_residual_large",
                "SOC 能量平衡残差异常偏大。",
                {"max_residual": max_residual},
            )
        elif max_residual > 1e-4:
            _add_health_issue(
                issues,
                "warning",
                "soc_energy_balance_residual_noticeable",
                "SOC 能量平衡残差超过常规数值误差。",
                {"max_residual": max_residual},
            )
    else:
        _add_health_issue(issues, "warning", "soc_energy_balance_not_available", "缺少逐日执行对象，无法检查 SOC 能量平衡。")

    return result


def _check_opendss_health(hourly_network_trace: dict[tuple[int, int], dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
    rows = list(hourly_network_trace.values())
    opendss_rows = [row for row in rows if bool(row.get("opendss_used"))]
    known_convergence = [row for row in opendss_rows if row.get("opendss_solve_converged") is not None]
    failed_convergence = [row for row in known_convergence if not bool(row.get("opendss_solve_converged"))]
    result = {
        "trace_hours": len(rows),
        "opendss_used_hours": len(opendss_rows),
        "convergence_known_hours": len(known_convergence),
        "failed_convergence_hours": len(failed_convergence),
    }

    if not rows:
        _add_health_issue(issues, "warning", "missing_opendss_trace", "未导出 OpenDSS 小时潮流 trace。")
    elif not opendss_rows:
        _add_health_issue(issues, "warning", "opendss_not_used_in_trace", "小时 trace 中未发现 OpenDSS 潮流结果。")
    elif not known_convergence:
        _add_health_issue(issues, "warning", "opendss_convergence_unknown", "OpenDSS trace 缺少收敛状态字段。")
    elif failed_convergence:
        _add_health_issue(
            issues,
            "error",
            "opendss_solve_not_converged",
            "存在 OpenDSS 潮流未收敛小时。",
            result,
        )

    return result


def _check_network_health(ann: Any, hourly_network_trace: dict[tuple[int, int], dict[str, Any]], issues: list[dict[str, Any]]) -> dict[str, Any]:
    ann_summary = ann.summary_dict() if ann is not None and hasattr(ann, "summary_dict") else {}
    result = {
        "global": {
            "baseline_voltage_violation_hours": _safe_float(ann_summary.get("baseline_hours_with_voltage_violation")),
            "with_storage_voltage_violation_hours": _safe_float(ann_summary.get("hours_with_voltage_violation")),
            "baseline_line_overload_hours": _safe_float(ann_summary.get("baseline_hours_with_line_overload")),
            "with_storage_line_overload_hours": _safe_float(ann_summary.get("hours_with_line_overload")),
            "baseline_transformer_overload_hours": _safe_float(ann_summary.get("baseline_transformer_violation_hours")),
            "with_storage_transformer_overload_hours": _safe_float(ann_summary.get("transformer_violation_hours")),
            "max_voltage_violation_pu": _safe_float(ann_summary.get("max_voltage_violation_pu")),
            "max_line_loading_pct": _safe_float(ann_summary.get("max_line_loading_pct")),
        },
        "target_connection": {
            "baseline_voltage_violation_hours": _safe_float(ann_summary.get("baseline_target_hours_with_voltage_violation")),
            "with_storage_voltage_violation_hours": _safe_float(ann_summary.get("target_hours_with_voltage_violation")),
            "baseline_line_overload_hours": _safe_float(ann_summary.get("baseline_target_hours_with_line_overload")),
            "with_storage_line_overload_hours": _safe_float(ann_summary.get("target_hours_with_line_overload")),
            "max_voltage_violation_pu": _safe_float(ann_summary.get("max_target_voltage_violation_pu")),
            "max_line_loading_pct": _safe_float(ann_summary.get("max_target_line_loading_pct")),
            "delta_safety_violation_hours": _safe_float(ann_summary.get("delta_target_safety_violation_hours")),
        },
    }

    if result["global"]["max_voltage_violation_pu"] > 0.20:
        _add_health_issue(issues, "error", "global_voltage_violation_extreme", "全网最大电压越限幅度异常偏大。", result["global"])
    if result["target_connection"]["max_voltage_violation_pu"] > 0.20:
        _add_health_issue(
            issues,
            "error",
            "target_voltage_violation_extreme",
            "储能接入点最大电压越限幅度异常偏大。",
            result["target_connection"],
        )
    if result["global"]["max_line_loading_pct"] > 500.0:
        _add_health_issue(issues, "warning", "global_line_loading_extreme", "全网最大线路负载率异常偏高。", result["global"])
    if result["target_connection"]["max_line_loading_pct"] > 500.0:
        _add_health_issue(
            issues,
            "warning",
            "target_line_loading_extreme",
            "储能接入线路最大负载率异常偏高。",
            result["target_connection"],
        )

    trace_rows = list(hourly_network_trace.values())
    result["trace_extrema"] = {
        "min_voltage_pu": min((_safe_float(row.get("voltage_pu_min"), 1.0) for row in trace_rows), default=None),
        "max_voltage_pu": max((_safe_float(row.get("voltage_pu_max"), 1.0) for row in trace_rows), default=None),
        "max_line_loading_pct": max((_safe_float(row.get("line_loading_max_pct")) for row in trace_rows), default=None),
        "max_target_line_loading_pct": max((_safe_float(row.get("target_line_loading_max_pct")) for row in trace_rows), default=None),
    }
    return result


def _check_economics_health(run_result: LemmingOptimizationRunResult, issues: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [
        item
        for item in list(getattr(run_result, "archive_results", None) or []) + list(getattr(run_result, "population_results", None) or [])
        if getattr(item, "lifecycle_financial_result", None) is not None
    ]
    core_keys = (
        "npv_yuan",
        "initial_investment_yuan",
        "annualized_net_cashflow_yuan",
        "annual_net_operating_cashflow_yuan",
    )
    optional_keys = ("irr", "simple_payback_years", "discounted_payback_years", "lc_net_profit_yuan")
    missing_core = 0
    nonfinite = 0
    abnormal = 0
    for item in evaluated:
        summary = _result_summary(item)
        for key in core_keys:
            value = _to_float(summary.get(key))
            if value is None:
                missing_core += 1
            elif not math.isfinite(value):
                nonfinite += 1
            elif abs(value) > 1.0e12:
                abnormal += 1
        for key in optional_keys:
            value = _to_float(summary.get(key))
            if value is not None and (not math.isfinite(value) or abs(value) > 1.0e12):
                abnormal += 1

    best_summary = _result_summary(getattr(run_result, "best_result", None))
    best_missing = [key for key in core_keys if _to_float(best_summary.get(key)) is None]
    result = {
        "evaluated_financial_result_count": len(evaluated),
        "missing_core_value_count": missing_core,
        "nonfinite_value_count": nonfinite,
        "abnormal_large_value_count": abnormal,
        "best_missing_core_keys": best_missing,
    }

    if best_missing:
        _add_health_issue(issues, "error", "best_economics_missing_core_values", "最优方案经济性核心字段缺失。", result)
    if nonfinite:
        _add_health_issue(issues, "error", "economics_nonfinite_values", "经济性结果存在 NaN/Inf。", result)
    if abnormal:
        _add_health_issue(issues, "warning", "economics_abnormal_large_values", "经济性结果存在异常大值。", result)
    if missing_core and not best_missing:
        _add_health_issue(issues, "warning", "economics_missing_values_in_candidates", "部分候选方案经济性字段缺失。", result)

    return result


def _build_run_health_report(
    run_result: LemmingOptimizationRunResult,
    hourly_network_trace: dict[tuple[int, int], dict[str, Any]],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    best = getattr(run_result, "best_result", None)
    ann = getattr(best, "annual_operation_result", None) if best is not None else None
    checks = {
        "feasibility": _check_feasibility_health(run_result, issues),
        "soc": _check_soc_health(ann, issues),
        "opendss": _check_opendss_health(hourly_network_trace, issues),
        "network": _check_network_health(ann, hourly_network_trace, issues),
        "economics": _check_economics_health(run_result, issues),
    }
    status = _health_status(issues)
    error_count = sum(1 for item in issues if item.get("severity") == "error" or item.get("level") == "critical")
    warning_count = sum(1 for item in issues if item.get("severity") == "warning" or item.get("level") == "warning")
    return {
        "report_type": "run_health",
        "status": status,
        "summary": {
            "issue_count": len(issues),
            "error_count": error_count,
            "critical_count": error_count,
            "warning_count": warning_count,
            "best_result_available": best is not None,
            "annual_operation_available": ann is not None,
        },
        "issue_counts": {
            "total": len(issues),
            "critical": error_count,
            "error": error_count,
            "warning": warning_count,
        },
        "checks": checks,
        "issues": issues,
    }


def _flatten_network_trace(ann: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[tuple[int, int], dict[str, Any]]]:
    bus_rows: list[dict[str, Any]] = []
    line_rows: list[dict[str, Any]] = []
    hourly: dict[tuple[int, int], dict[str, Any]] = {}
    for exec_result in getattr(ann, "daily_exec_objects", None) or []:
        fallback_day = int(getattr(exec_result, "day_index", 0)) + 1
        for trace in getattr(exec_result, "network_trace", None) or []:
            day_index = int(trace.get("day_index") or fallback_day)
            hour = int(trace.get("hour") or 0)
            key = (day_index, hour)
            hourly[key] = {
                "baseline_voltage_pu_min": trace.get("baseline_voltage_pu_min"),
                "baseline_voltage_pu_max": trace.get("baseline_voltage_pu_max"),
                "baseline_voltage_violation_pu": trace.get("baseline_voltage_violation_pu"),
                "baseline_line_current_max_a": trace.get("baseline_line_current_max_a"),
                "baseline_line_loading_max_pct": trace.get("baseline_line_loading_max_pct"),
                "baseline_target_voltage_pu_min": trace.get("baseline_target_voltage_pu_min"),
                "baseline_target_voltage_pu_max": trace.get("baseline_target_voltage_pu_max"),
                "baseline_target_voltage_violation_pu": trace.get("baseline_target_voltage_violation_pu"),
                "baseline_target_line_current_max_a": trace.get("baseline_target_line_current_max_a"),
                "baseline_target_line_loading_max_pct": trace.get("baseline_target_line_loading_max_pct"),
                "baseline_target_line_overload_pct": trace.get("baseline_target_line_overload_pct"),
                "voltage_pu_min": trace.get("voltage_pu_min"),
                "voltage_pu_max": trace.get("voltage_pu_max"),
                "voltage_violation_pu": trace.get("voltage_violation_pu"),
                "storage_voltage_violation_increment_pu": trace.get("storage_voltage_violation_increment_pu"),
                "target_voltage_pu_min": trace.get("target_voltage_pu_min"),
                "target_voltage_pu_max": trace.get("target_voltage_pu_max"),
                "target_voltage_violation_pu": trace.get("target_voltage_violation_pu"),
                "storage_target_voltage_violation_increment_pu": trace.get(
                    "storage_target_voltage_violation_increment_pu"
                ),
                "line_current_max_a": trace.get("line_current_max_a"),
                "line_loading_max_pct": trace.get("line_loading_max_pct"),
                "target_line_current_max_a": trace.get("target_line_current_max_a"),
                "target_line_loading_max_pct": trace.get("target_line_loading_max_pct"),
                "target_line_overload_pct": trace.get("target_line_overload_pct"),
                "storage_target_line_overload_increment_pct": trace.get("storage_target_line_overload_increment_pct"),
                "opendss_used": trace.get("opendss_used"),
                "opendss_baseline_converged": trace.get("opendss_baseline_converged"),
                "opendss_storage_converged": trace.get("opendss_storage_converged"),
                "opendss_solve_converged": trace.get("opendss_solve_converged"),
                "target_bus": trace.get("target_bus"),
                "target_load": trace.get("target_load"),
                "opendss_loss_baseline_kw": trace.get("opendss_loss_baseline_kw"),
                "opendss_loss_baseline_kvar": trace.get("opendss_loss_baseline_kvar"),
                "opendss_loss_with_storage_kw": trace.get("opendss_loss_with_storage_kw"),
                "opendss_loss_with_storage_kvar": trace.get("opendss_loss_with_storage_kvar"),
                "opendss_loss_reduction_kw": trace.get("opendss_loss_reduction_kw"),
                "opendss_loss_reduction_kwh": trace.get("opendss_loss_reduction_kwh"),
                "opendss_loss_reduction_positive_kwh": trace.get("opendss_loss_reduction_positive_kwh"),
                "opendss_loss_source": trace.get("opendss_loss_source"),
            }
            baseline_by_bus = {
                str(row.get("bus")): row
                for row in trace.get("baseline_bus_voltages") or []
                if isinstance(row, dict) and row.get("bus") is not None
            }
            for row in trace.get("bus_voltages") or []:
                if not isinstance(row, dict):
                    continue
                baseline = baseline_by_bus.get(str(row.get("bus"))) or {}
                baseline_violation = _voltage_violation_pu(
                    baseline.get("voltage_pu_min"),
                    baseline.get("voltage_pu_max"),
                )
                storage_violation = _voltage_violation_pu(
                    row.get("voltage_pu_min"),
                    row.get("voltage_pu_max"),
                )
                bus_rows.append(
                    {
                        "day_index": day_index,
                        "hour": hour,
                        "bus": row.get("bus"),
                        "baseline_voltage_pu_min": baseline.get("voltage_pu_min"),
                        "baseline_voltage_pu_max": baseline.get("voltage_pu_max"),
                        "voltage_pu_min": row.get("voltage_pu_min"),
                        "voltage_pu_max": row.get("voltage_pu_max"),
                        "storage_voltage_violation_increment_pu": max(0.0, storage_violation - baseline_violation),
                        "target_bus": trace.get("target_bus"),
                        "target_load": trace.get("target_load"),
                        "opendss_used": trace.get("opendss_used"),
                    }
                )
            for row in trace.get("line_currents") or []:
                if not isinstance(row, dict):
                    continue
                baseline_line_by_name = {
                    str(item.get("line")): item
                    for item in trace.get("baseline_line_currents") or []
                    if isinstance(item, dict) and item.get("line") is not None
                }
                baseline_line = baseline_line_by_name.get(str(row.get("line"))) or {}
                line_rows.append(
                    {
                        "day_index": day_index,
                        "hour": hour,
                        "line": row.get("line"),
                        "bus1": row.get("bus1"),
                        "bus2": row.get("bus2"),
                        "baseline_current_a": baseline_line.get("current_a"),
                        "baseline_loading_pct": baseline_line.get("loading_pct"),
                        "current_a": row.get("current_a"),
                        "loading_pct": row.get("loading_pct"),
                        "normamps": row.get("normamps"),
                        "emergamps": row.get("emergamps"),
                        "terminal1_power_kw": row.get("terminal1_power_kw"),
                        "flow_direction": row.get("flow_direction"),
                        "target_bus": trace.get("target_bus"),
                        "target_load": trace.get("target_load"),
                        "opendss_used": trace.get("opendss_used"),
                    }
                )
    return bus_rows, line_rows, hourly


def export_optimization_run(
    output_dir: str | Path,
    run_result: LemmingOptimizationRunResult,
    case_name: str | None = None,
    enable_plots: bool = True,
) -> dict[str, str]:
    out_dir = _ensure_dir(output_dir)
    case_name = case_name or out_dir.name

    archive_df = OptimizerBridge.results_to_dataframe(run_result.archive_results)
    pop_df = OptimizerBridge.results_to_dataframe(run_result.population_results)
    history_df = pd.DataFrame(run_result.history)

    archive_path = out_dir / "archive_results.csv"
    population_path = out_dir / "population_results.csv"
    history_path = out_dir / "optimization_history.csv"

    archive_df.to_csv(archive_path, index=False, encoding="utf-8-sig")
    pop_df.to_csv(population_path, index=False, encoding="utf-8-sig")
    history_df.to_csv(history_path, index=False, encoding="utf-8-sig")

    best_result_path = out_dir / "best_result_summary.json"
    best_annual_summary_path = out_dir / "best_annual_summary.csv"
    best_financial_summary_path = out_dir / "best_financial_summary.csv"
    best_cashflow_table_path = out_dir / "best_cashflow_table.csv"
    best_monthly_summary_path = out_dir / "best_monthly_summary.csv"
    best_hourly_path = out_dir / "best_annual_hourly_operation.csv"
    best_bus_voltage_path = out_dir / "best_bus_voltage_trace.csv"
    best_line_loading_path = out_dir / "best_line_loading_trace.csv"
    best_network_loss_path = out_dir / "best_network_loss_trace.csv"
    configuration_report_path = out_dir / "configuration_report.json"
    operation_report_path = out_dir / "operation_report.json"
    financial_report_path = out_dir / "financial_report.json"
    network_impact_report_path = out_dir / "network_impact_report.json"
    run_health_report_path = out_dir / "run_health_report.json"

    plot_paths: list[str] = []
    best_hourly_network_trace: dict[tuple[int, int], dict[str, Any]] = {}

    if run_result.best_result is not None:
        best_summary = run_result.best_result.summary_dict()
        _safe_write_json(best_result_path, best_summary)
        _safe_write_json(configuration_report_path, _build_configuration_report(run_result.best_result, case_name))

        ann = run_result.best_result.annual_operation_result
        fin = run_result.best_result.lifecycle_financial_result

        if ann is not None:
            pd.DataFrame([ann.summary_dict()]).to_csv(best_annual_summary_path, index=False, encoding="utf-8-sig")
            ann.monthly_summary_dataframe().to_csv(best_monthly_summary_path, index=False, encoding="utf-8-sig")
            bus_trace_rows, line_trace_rows, hourly_network_trace = _flatten_network_trace(ann)
            best_hourly_network_trace = hourly_network_trace

            hourly_rows = []
            for d in range(365):
                for h in range(24):
                    row = {
                        "day_index": d + 1,
                        "hour": h,
                        "tariff_yuan_per_kwh": ann.tariff_yuan_per_kwh[d, h],
                        "actual_net_load_kw": ann.actual_net_load_kw[d, h],
                        "grid_exchange_kw": ann.grid_exchange_kw[d, h],
                        "plan_charge_kw": ann.plan_charge_kw[d, h],
                        "plan_discharge_kw": ann.plan_discharge_kw[d, h],
                        "exec_charge_kw": ann.exec_charge_kw[d, h],
                        "exec_discharge_kw": ann.exec_discharge_kw[d, h],
                        "soc_open": ann.soc_hourly_path[d, h],
                        "soc_close": ann.soc_hourly_path[d, h + 1],
                        "arbitrage_revenue_yuan": ann.arbitrage_revenue_yuan[d, h],
                        "service_capacity_revenue_yuan": ann.service_capacity_revenue_yuan[d, h],
                        "service_delivery_revenue_yuan": ann.service_delivery_revenue_yuan[d, h],
                        "service_penalty_yuan": ann.service_penalty_yuan[d, h],
                        "degradation_cost_yuan": ann.degradation_cost_yuan[d, h],
                        "transformer_penalty_yuan": ann.transformer_penalty_yuan[d, h],
                        "voltage_penalty_yuan": ann.voltage_penalty_yuan[d, h],
                    }
                    row.update(hourly_network_trace.get((d + 1, h), {}))
                    hourly_rows.append(row)
            pd.DataFrame(hourly_rows).to_csv(best_hourly_path, index=False, encoding="utf-8-sig")
            if bus_trace_rows:
                pd.DataFrame(bus_trace_rows).to_csv(best_bus_voltage_path, index=False, encoding="utf-8-sig")
            if line_trace_rows:
                pd.DataFrame(line_trace_rows).to_csv(best_line_loading_path, index=False, encoding="utf-8-sig")
            network_loss_rows = [
                {"day_index": day, "hour": hour, **row}
                for (day, hour), row in sorted(hourly_network_trace.items())
                if row.get("opendss_loss_baseline_kw") is not None
                or row.get("opendss_loss_with_storage_kw") is not None
                or row.get("opendss_loss_reduction_kwh") is not None
            ]
            if network_loss_rows:
                pd.DataFrame(network_loss_rows).to_csv(best_network_loss_path, index=False, encoding="utf-8-sig")
            _safe_write_json(operation_report_path, _build_operation_report(ann))
            _safe_write_json(
                network_impact_report_path,
                _build_network_impact_report(ann, hourly_network_trace, bus_trace_rows, line_trace_rows),
            )

        if fin is not None:
            pd.DataFrame([fin.summary_dict()]).to_csv(best_financial_summary_path, index=False, encoding="utf-8-sig")
            fin.cashflow_dataframe().to_csv(best_cashflow_table_path, index=False, encoding="utf-8-sig")
            _safe_write_json(financial_report_path, _build_financial_report(fin, ann))

        if enable_plots:
            fig_root = _ensure_dir(out_dir / "figures")
            plot_paths.extend(plot_pareto_front(case_name=case_name, run_result=run_result, output_dir=fig_root / "optimization"))
            plot_paths.extend(plot_scheme_overview(case_name=case_name, best_result=run_result.best_result, output_dir=fig_root / "scheme"))
            if ann is not None:
                plot_paths.extend(plot_dispatch_profiles(case_name=case_name, annual_result=ann, output_dir=fig_root / "dispatch"))
            if fin is not None:
                plot_paths.extend(plot_financial_diagnostics(case_name=case_name, financial_result=fin, output_dir=fig_root / "economics"))

    meta = {
        "archive_size": len(run_result.archive_results),
        "population_size": len(run_result.population_results),
        "all_evaluation_count": run_result.all_evaluation_count,
        "plot_count": len(plot_paths),
    }
    _safe_write_json(out_dir / "run_meta.json", meta)
    _safe_write_json(run_health_report_path, _build_run_health_report(run_result, best_hourly_network_trace))

    if plot_paths:
        pd.DataFrame({"plot_path": plot_paths}).to_csv(out_dir / "generated_plots.csv", index=False, encoding="utf-8-sig")

    out: dict[str, str] = {
        "archive_results": str(archive_path),
        "population_results": str(population_path),
        "history": str(history_path),
        "best_result_summary": str(best_result_path),
        "run_meta": str(out_dir / "run_meta.json"),
        "run_health_report": str(run_health_report_path),
    }
    if run_result.best_result is not None:
        out.update(
            {
                "best_annual_summary": str(best_annual_summary_path),
                "best_financial_summary": str(best_financial_summary_path),
                "best_cashflow_table": str(best_cashflow_table_path),
                "best_monthly_summary": str(best_monthly_summary_path),
                "best_annual_hourly_operation": str(best_hourly_path),
                "configuration_report": str(configuration_report_path),
            }
        )
        if operation_report_path.exists():
            out["operation_report"] = str(operation_report_path)
        if financial_report_path.exists():
            out["financial_report"] = str(financial_report_path)
        if network_impact_report_path.exists():
            out["network_impact_report"] = str(network_impact_report_path)
        if best_bus_voltage_path.exists():
            out["best_bus_voltage_trace"] = str(best_bus_voltage_path)
        if best_line_loading_path.exists():
            out["best_line_loading_trace"] = str(best_line_loading_path)
        if best_network_loss_path.exists():
            out["best_network_loss_trace"] = str(best_network_loss_path)
    if plot_paths:
        out["generated_plots"] = str(out_dir / "generated_plots.csv")

    return out
