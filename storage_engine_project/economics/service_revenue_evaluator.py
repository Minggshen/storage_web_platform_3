
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.economics.economic_result_models import AnnualRevenueAuditResult
from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationResult

def _meta_float(meta: dict, key: str, default: float) -> float:
    try:
        value = meta.get(key, default)
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _meta_float_any(meta: dict, keys: tuple[str, ...], default: float) -> float:
    for key in keys:
        if key in meta:
            return _meta_float(meta, key, default)
    return float(default)


@dataclass(slots=True)
class AnnualRevenueAuditConfig:
    """
    年度收益审计配置。
    """

    default_om_ratio_annual: float = 0.02
    use_strategy_om_ratio: bool = True

    # 与前端全局经济参数保持一致；registry 缺字段时才作为兜底。
    default_fixed_om_yuan_per_kw_year: float = 18.0
    default_variable_om_yuan_per_kwh: float = 0.004

    use_fixed_and_variable_om: bool = True
    recompute_demand_saving_if_missing: bool = True
    default_capacity_revenue_days: float = 365.0
    default_network_loss_proxy_rate: float = 0.02


class AnnualRevenueAuditor:
    def __init__(self, config: AnnualRevenueAuditConfig | None = None) -> None:
        self.config = config or AnnualRevenueAuditConfig()

    def evaluate(
        self,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult,
        initial_capex_yuan: float,
    ) -> AnnualRevenueAuditResult:
        strategy = ctx.strategy
        cfg = self.config
        meta = dict(ctx.meta)

        fixed_om_yuan_per_kw_year = _meta_float(
            meta,
            "annual_fixed_om_yuan_per_kw_year",
            float(cfg.default_fixed_om_yuan_per_kw_year),
        )
        variable_om_yuan_per_kwh = _meta_float(
            meta,
            "annual_variable_om_yuan_per_kwh",
            float(cfg.default_variable_om_yuan_per_kwh),
        )
        demand_charge_yuan_per_kw_month = _meta_float(
            meta,
            "demand_charge_yuan_per_kw_month",
            float(getattr(ctx, "daily_demand_charge_yuan_per_kw", 0.0)),
        )

        om_ratio = (
            float(getattr(strategy, "om_ratio_annual", 0.0))
            if cfg.use_strategy_om_ratio
            else float(cfg.default_om_ratio_annual)
        )
        if om_ratio <= 0:
            om_ratio = float(cfg.default_om_ratio_annual)

        annual_om_cost_yuan_ratio = float(initial_capex_yuan) * om_ratio
        annual_om_cost_yuan_fixed_var = (
            float(annual_result.rated_power_kw) * fixed_om_yuan_per_kw_year
            + float(annual_result.annual_battery_throughput_kwh) * variable_om_yuan_per_kwh
        )
        annual_om_cost_yuan = (
            annual_om_cost_yuan_fixed_var if cfg.use_fixed_and_variable_om else annual_om_cost_yuan_ratio
        )

        include_service = bool(getattr(ctx, "include_aux_service_revenue", False))
        include_degradation = bool(getattr(ctx, "include_degradation_cost", True))
        include_demand = bool(meta.get("include_demand_saving", True))

        annual_arbitrage_revenue_yuan = float(annual_result.annual_arbitrage_revenue_yuan)

        if include_service:
            annual_service_capacity_revenue_yuan = float(annual_result.annual_service_capacity_revenue_yuan)
            annual_service_delivery_revenue_yuan = float(annual_result.annual_service_delivery_revenue_yuan)
            annual_service_penalty_yuan = float(annual_result.annual_service_penalty_yuan)
        else:
            annual_service_capacity_revenue_yuan = 0.0
            annual_service_delivery_revenue_yuan = 0.0
            annual_service_penalty_yuan = 0.0

        annual_demand_saving_yuan = float(annual_result.annual_demand_saving_yuan)
        demand_source = "kernel"
        if include_demand and cfg.recompute_demand_saving_if_missing and abs(annual_demand_saving_yuan) <= 1e-9:
            annual_demand_saving_yuan = self._compute_demand_saving_from_peaks(
                annual_result=annual_result,
                annual_start_date=str(meta.get("annual_start_date", f"{int(getattr(ctx, 'model_year', 2025))}-01-01")),
                demand_charge_yuan_per_kw_month=max(0.0, float(demand_charge_yuan_per_kw_month)),
            )
            demand_source = "auditor_recomputed"
        elif not include_demand:
            annual_demand_saving_yuan = 0.0
            demand_source = "disabled"

        annual_capacity_revenue_yuan, monthly_capacity_revenue, capacity_meta = self._compute_capacity_revenue(
            ctx=ctx,
            annual_result=annual_result,
        )
        annual_loss_reduction_revenue_yuan, monthly_loss_reduction_revenue, loss_meta = self._compute_loss_reduction_revenue(
            ctx=ctx,
            annual_result=annual_result,
        )

        annual_degradation_cost_yuan = float(annual_result.annual_degradation_cost_yuan) if include_degradation else 0.0
        annual_transformer_penalty_yuan = float(annual_result.annual_transformer_penalty_yuan)
        annual_voltage_penalty_yuan = float(annual_result.annual_voltage_penalty_yuan)

        annual_service_net_revenue_yuan = (
            annual_service_capacity_revenue_yuan
            + annual_service_delivery_revenue_yuan
            - annual_service_penalty_yuan
        )

        annual_gross_revenue_yuan = (
            annual_arbitrage_revenue_yuan
            + annual_service_capacity_revenue_yuan
            + annual_service_delivery_revenue_yuan
            + annual_demand_saving_yuan
            + annual_capacity_revenue_yuan
            + annual_loss_reduction_revenue_yuan
        )

        annual_operating_cost_yuan = (
            annual_service_penalty_yuan
            + annual_degradation_cost_yuan
            + annual_transformer_penalty_yuan
            + annual_voltage_penalty_yuan
            + annual_om_cost_yuan
        )

        annual_net_before_om_yuan = (
            annual_arbitrage_revenue_yuan
            + annual_service_capacity_revenue_yuan
            + annual_service_delivery_revenue_yuan
            + annual_demand_saving_yuan
            + annual_capacity_revenue_yuan
            + annual_loss_reduction_revenue_yuan
            - annual_service_penalty_yuan
            - annual_degradation_cost_yuan
            - annual_transformer_penalty_yuan
            - annual_voltage_penalty_yuan
        )
        annual_net_after_om_yuan = annual_net_before_om_yuan - annual_om_cost_yuan

        annual_result.metadata["annual_capacity_revenue_yuan"] = float(annual_capacity_revenue_yuan)
        annual_result.metadata["annual_loss_reduction_revenue_yuan"] = float(annual_loss_reduction_revenue_yuan)
        annual_result.metadata["monthly_capacity_revenue_yuan"] = [
            float(x) for x in np.asarray(monthly_capacity_revenue, dtype=float).reshape(12)
        ]
        annual_result.metadata["monthly_loss_reduction_revenue_yuan"] = [
            float(x) for x in np.asarray(monthly_loss_reduction_revenue, dtype=float).reshape(12)
        ]
        annual_result.metadata.update(capacity_meta)
        annual_result.metadata.update(loss_meta)

        monthly_summary = annual_result.monthly_summary_dataframe()
        if not isinstance(monthly_summary, pd.DataFrame):
            monthly_summary = pd.DataFrame()

        return AnnualRevenueAuditResult(
            internal_model_id=annual_result.internal_model_id,
            strategy_id=annual_result.strategy_id,
            strategy_name=annual_result.strategy_name,
            rated_power_kw=float(annual_result.rated_power_kw),
            rated_energy_kwh=float(annual_result.rated_energy_kwh),
            effective_power_cap_kw=float(annual_result.effective_power_cap_kw),
            annual_arbitrage_revenue_yuan=float(annual_arbitrage_revenue_yuan),
            annual_service_capacity_revenue_yuan=float(annual_service_capacity_revenue_yuan),
            annual_service_delivery_revenue_yuan=float(annual_service_delivery_revenue_yuan),
            annual_service_penalty_yuan=float(annual_service_penalty_yuan),
            annual_demand_saving_yuan=float(annual_demand_saving_yuan),
            annual_capacity_revenue_yuan=float(annual_capacity_revenue_yuan),
            annual_loss_reduction_revenue_yuan=float(annual_loss_reduction_revenue_yuan),
            annual_degradation_cost_yuan=float(annual_degradation_cost_yuan),
            annual_transformer_penalty_yuan=float(annual_transformer_penalty_yuan),
            annual_voltage_penalty_yuan=float(annual_voltage_penalty_yuan),
            annual_om_cost_yuan=float(annual_om_cost_yuan),
            annual_gross_revenue_yuan=float(annual_gross_revenue_yuan),
            annual_service_net_revenue_yuan=float(annual_service_net_revenue_yuan),
            annual_operating_cost_yuan=float(annual_operating_cost_yuan),
            annual_net_operating_cashflow_before_om_yuan=float(annual_net_before_om_yuan),
            annual_net_operating_cashflow_after_om_yuan=float(annual_net_after_om_yuan),
            annual_battery_throughput_kwh=float(annual_result.annual_battery_throughput_kwh),
            annual_equivalent_full_cycles=float(annual_result.annual_equivalent_full_cycles),
            transformer_violation_hours=float(annual_result.transformer_violation_hours),
            max_transformer_slack_kw=float(annual_result.max_transformer_slack_kw),
            monthly_summary=monthly_summary,
            metadata={
                "om_ratio_annual": float(om_ratio),
                "annual_om_cost_yuan_ratio_method": float(annual_om_cost_yuan_ratio),
                "annual_om_cost_yuan_fixed_var_method": float(annual_om_cost_yuan_fixed_var),
                "annual_fixed_om_yuan_per_kw_year": float(fixed_om_yuan_per_kw_year),
                "annual_variable_om_yuan_per_kwh": float(variable_om_yuan_per_kwh),
                "include_service": include_service,
                "include_degradation": include_degradation,
                "demand_saving_source": demand_source,
                "demand_charge_yuan_per_kw_month_effective": float(max(0.0, demand_charge_yuan_per_kw_month)),
                "annual_demand_saving_kw_month_effective": float(
                    annual_demand_saving_yuan / max(float(demand_charge_yuan_per_kw_month), 1e-9)
                    if demand_charge_yuan_per_kw_month > 0
                    else 0.0
                ),
                **capacity_meta,
                **loss_meta,
            },
        )

    def _compute_capacity_revenue(
        self,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult,
    ) -> tuple[float, np.ndarray, dict[str, float | bool]]:
        include_capacity = bool(getattr(ctx, "include_capacity_revenue", False))
        if not include_capacity:
            return 0.0, np.zeros(12, dtype=float), {
                "include_capacity_revenue": False,
                "capacity_service_price_yuan_per_kw_day_effective": 0.0,
                "capacity_revenue_eligible_days_effective": 0.0,
            }

        meta = dict(ctx.meta)
        price = _meta_float_any(
            meta,
            (
                "capacity_service_price_yuan_per_kw_day",
                "capacity_revenue_yuan_per_kw_day",
                "price_cap_daily",
            ),
            0.0,
        )
        eligible_days = _meta_float(meta, "capacity_revenue_eligible_days", self.config.default_capacity_revenue_days)
        capacity_kw = _meta_float(
            meta,
            "capacity_revenue_kw",
            float(getattr(annual_result, "effective_power_cap_kw", annual_result.rated_power_kw)),
        )

        price = max(0.0, float(price))
        eligible_days = max(0.0, min(float(eligible_days), float(getattr(annual_result, "annual_days", 365) or 365)))
        capacity_kw = max(0.0, float(capacity_kw))
        annual_revenue = capacity_kw * price * eligible_days

        dates = pd.date_range(
            str(meta.get("annual_start_date", f"{int(getattr(ctx, 'model_year', 2025))}-01-01")),
            periods=365,
            freq="D",
        )
        month_days = np.array([(dates.month == m).sum() for m in range(1, 13)], dtype=float)
        day_scale = eligible_days / max(float(np.sum(month_days)), 1.0)
        monthly = capacity_kw * price * month_days * day_scale
        return float(annual_revenue), monthly, {
            "include_capacity_revenue": True,
            "capacity_service_price_yuan_per_kw_day_effective": float(price),
            "capacity_revenue_eligible_days_effective": float(eligible_days),
            "capacity_revenue_kw_effective": float(capacity_kw),
        }

    def _compute_loss_reduction_revenue(
        self,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult,
    ) -> tuple[float, np.ndarray, dict]:
        include_loss = bool(getattr(ctx, "include_loss_reduction_revenue", False))
        if not include_loss:
            return 0.0, np.zeros(12, dtype=float), {
                "include_loss_reduction_revenue": False,
                "network_loss_price_yuan_per_kwh_effective": 0.0,
                "annual_loss_reduction_kwh": 0.0,
            }

        meta = dict(ctx.meta)

        price = _meta_float_any(
            meta,
            ("network_loss_price_yuan_per_kwh", "loss_reduction_price_yuan_per_kwh", "price_loss"),
            0.0,
        )
        proxy_rate = _meta_float_any(
            meta,
            ("network_loss_proxy_rate", "loss_reduction_proxy_rate"),
            float(self.config.default_network_loss_proxy_rate),
        )
        direct_kwh = _meta_float(meta, "annual_loss_reduction_kwh", np.nan)
        annual_start_date = str(meta.get("annual_start_date", f"{int(getattr(ctx, 'model_year', 2025))}-01-01"))
        dates = pd.date_range(annual_start_date, periods=365, freq="D")
        month_idx = dates.month.values
        monthly_kwh = np.zeros(12, dtype=float)
        quantity_source = "proxy_quadratic_import"

        opendss_monthly_kwh = self._monthly_opendss_loss_reduction_kwh(
            annual_result=annual_result,
            annual_start_date=annual_start_date,
        )
        if opendss_monthly_kwh is not None:
            monthly_kwh = opendss_monthly_kwh
            quantity_source = "opendss_system_losses"
        elif np.isfinite(direct_kwh) and abs(float(direct_kwh)) > 1e-9:
            month_days = np.array([(month_idx == m).sum() for m in range(1, 13)], dtype=float)
            monthly_kwh = float(direct_kwh) * month_days / max(float(np.sum(month_days)), 1.0)
            quantity_source = "annual_loss_reduction_kwh"
        else:
            baseline_import = np.maximum(np.asarray(annual_result.baseline_net_load_kw, dtype=float), 0.0)
            actual_import = np.maximum(np.asarray(annual_result.grid_exchange_kw, dtype=float), 0.0)
            reference_kw = _meta_float(
                meta,
                "network_loss_reference_kw",
                max(float(np.max(baseline_import)) if baseline_import.size else 0.0, 1.0),
            )
            reference_kw = max(1.0, float(reference_kw))
            proxy_rate = max(0.0, float(proxy_rate))
            baseline_loss_proxy = (baseline_import ** 2) / reference_kw * proxy_rate
            actual_loss_proxy = (actual_import ** 2) / reference_kw * proxy_rate
            for month in range(1, 13):
                mask = month_idx == month
                if not np.any(mask):
                    continue
                monthly_kwh[month - 1] = max(
                    0.0,
                    float(np.sum(baseline_loss_proxy[mask]) - np.sum(actual_loss_proxy[mask])),
                )

        price = max(0.0, float(price))
        monthly = monthly_kwh * price
        annual_revenue = float(np.sum(monthly))
        return annual_revenue, monthly, {
            "include_loss_reduction_revenue": True,
            "network_loss_price_yuan_per_kwh_effective": float(price),
            "network_loss_proxy_rate_effective": float(max(0.0, proxy_rate)),
            "annual_loss_reduction_kwh": float(np.sum(monthly_kwh)),
            "monthly_loss_reduction_kwh": [float(x) for x in monthly_kwh],
            "network_loss_quantity_source_effective": quantity_source,
        }

    @staticmethod
    def _monthly_opendss_loss_reduction_kwh(
        annual_result: AnnualOperationResult,
        annual_start_date: str,
    ) -> np.ndarray | None:
        daily_execs = getattr(annual_result, "daily_exec_objects", None) or []
        if not daily_execs:
            return None

        dates = pd.date_range(annual_start_date, periods=365, freq="D")
        monthly_kwh = np.zeros(12, dtype=float)
        seen = 0
        for exec_result in daily_execs:
            fallback_day = int(getattr(exec_result, "day_index", 0)) + 1
            for trace in getattr(exec_result, "network_trace", None) or []:
                if not isinstance(trace, dict) or not trace.get("opendss_used", False):
                    continue
                value = trace.get("opendss_loss_reduction_kwh")
                try:
                    loss_reduction_kwh = float(value)
                except Exception:
                    continue
                if not np.isfinite(loss_reduction_kwh):
                    continue
                try:
                    day_index = int(trace.get("day_index") or fallback_day)
                except Exception:
                    continue
                if day_index < 1 or day_index > 365:
                    continue
                month = int(dates[day_index - 1].month)
                monthly_kwh[month - 1] += loss_reduction_kwh
                seen += 1

        return monthly_kwh if seen else None

    @staticmethod
    def _compute_demand_saving_from_peaks(
        annual_result: AnnualOperationResult,
        annual_start_date: str,
        demand_charge_yuan_per_kw_month: float,
    ) -> float:
        if demand_charge_yuan_per_kw_month <= 0:
            return 0.0

        dates = pd.date_range(annual_start_date, periods=365, freq="D")
        month_idx = dates.month.values
        baseline_import = np.maximum(np.asarray(annual_result.baseline_net_load_kw, dtype=float), 0.0)
        actual_import = np.maximum(np.asarray(annual_result.grid_exchange_kw, dtype=float), 0.0)

        total = 0.0
        for month in range(1, 13):
            mask = month_idx == month
            if not np.any(mask):
                continue
            baseline_peak = float(np.max(baseline_import[mask]))
            actual_peak = float(np.max(actual_import[mask]))
            reduction_kw = max(0.0, baseline_peak - actual_peak)
            total += reduction_kw * float(demand_charge_yuan_per_kw_month)
        return float(total)
