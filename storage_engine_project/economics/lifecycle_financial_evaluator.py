
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.economics.economic_result_models import (
    AnnualRevenueAuditResult,
    CapitalCostBreakdown,
    LifecycleCashflowTable,
    LifecycleFinancialResult,
)
from storage_engine_project.economics.service_revenue_evaluator import (
    AnnualRevenueAuditConfig,
    AnnualRevenueAuditor,
)
from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationResult

def _meta_float(meta: dict[str, Any], key: str, default: float) -> float:
    try:
        value = meta.get(key, default)
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _meta_int(meta: dict[str, Any], key: str, default: int | None) -> int | None:
    value = meta.get(key, default)
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except Exception:
        return default


@dataclass(slots=True)
class LifecycleFinancialConfig:
    project_life_years: int = 15
    discount_rate: float = 0.08

    annual_revenue_growth_rate: float = 0.00
    annual_om_growth_rate: float = 0.02

    enable_replacement: bool = True
    default_replacement_year_if_missing: int | None = None
    replacement_cost_ratio: float = 0.60
    default_cycle_life_efc: float = 8000.0
    default_calendar_life_years: float = 20.0
    default_calendar_fade_share: float = 0.15
    replacement_trigger_soh: float = 0.70
    replacement_reset_soh: float = 0.95

    default_safety_markup_ratio: float = 0.00
    default_integration_markup_ratio: float = 0.00
    default_other_capex_yuan: float = 0.0

    include_salvage_value: bool = True

    irr_search_low: float = -0.95
    irr_search_high: float = 3.00
    irr_max_iter: int = 200
    irr_tol: float = 1e-8

    use_strategy_metadata_overrides: bool = True
    use_context_meta_overrides: bool = True


class LifecycleFinancialEvaluator:
    def __init__(
        self,
        config: LifecycleFinancialConfig | None = None,
        annual_revenue_auditor: AnnualRevenueAuditor | None = None,
    ) -> None:
        self.config = config or LifecycleFinancialConfig()
        self.annual_revenue_auditor = annual_revenue_auditor or AnnualRevenueAuditor(
            AnnualRevenueAuditConfig()
        )

    def evaluate(
        self,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult,
    ) -> LifecycleFinancialResult:
        cfg = self.config
        meta = dict(ctx.meta)

        capex_breakdown = self._build_initial_capex_breakdown(
            ctx=ctx,
            rated_power_kw=float(annual_result.rated_power_kw),
            rated_energy_kwh=float(annual_result.rated_energy_kwh),
        )
        initial_investment_yuan = float(capex_breakdown.total_capex_yuan)

        annual_audit = self.annual_revenue_auditor.evaluate(
            ctx=ctx,
            annual_result=annual_result,
            initial_capex_yuan=initial_investment_yuan,
        )

        project_life_years = self._resolve_project_life_years(ctx)
        discount_rate = self._resolve_discount_rate(ctx)
        include_replacement = bool(cfg.enable_replacement and getattr(ctx, "include_replacement_cost", True))

        government_subsidy_yuan = self._resolve_government_subsidy(
            ctx=ctx,
            rated_power_kw=float(annual_result.rated_power_kw),
            rated_energy_kwh=float(annual_result.rated_energy_kwh),
            initial_investment_yuan=initial_investment_yuan,
        )
        initial_net_investment_yuan = max(0.0, initial_investment_yuan - government_subsidy_yuan)

        cashflow_table = self._build_lifecycle_cashflow_table(
            ctx=ctx,
            annual_result=annual_result,
            annual_audit=annual_audit,
            initial_investment_yuan=initial_investment_yuan,
            project_life_years=project_life_years,
            include_replacement=include_replacement,
        )

        npv_yuan = self._compute_npv_from_cashflow_table(
            initial_investment_yuan=initial_net_investment_yuan,
            cashflow_table=cashflow_table,
        )

        irr = self._compute_irr(
            initial_investment_yuan=initial_net_investment_yuan,
            annual_net_cashflows_yuan=cashflow_table.net_cashflow_yuan,
            search_low=float(cfg.irr_search_low),
            search_high=float(cfg.irr_search_high),
            max_iter=int(cfg.irr_max_iter),
            tol=float(cfg.irr_tol),
        )

        simple_payback = self._compute_payback_years(
            initial_investment_yuan=initial_net_investment_yuan,
            cashflows=cashflow_table.net_cashflow_yuan,
        )
        discounted_payback = self._compute_payback_years(
            initial_investment_yuan=initial_net_investment_yuan,
            cashflows=cashflow_table.discounted_net_cashflow_yuan,
        )

        total_replacement = float(np.sum(cashflow_table.replacement_cost_yuan))
        total_salvage = float(np.sum(cashflow_table.salvage_value_yuan))
        annualized_net_cashflow = float(np.mean(cashflow_table.net_cashflow_yuan))
        lc_net_profit = float(np.sum(cashflow_table.net_cashflow_yuan) - initial_net_investment_yuan)

        replacement_equivalent_annual = total_replacement / max(1, int(project_life_years))
        salvage_equivalent_annual = total_salvage / max(1, int(project_life_years))
        annual_net_cashflow_after_replacement_equivalent_yuan = (
            float(annual_audit.annual_net_operating_cashflow_after_om_yuan)
            - float(replacement_equivalent_annual)
            + float(salvage_equivalent_annual)
        )

        result = LifecycleFinancialResult(
            internal_model_id=annual_result.internal_model_id,
            strategy_id=annual_result.strategy_id,
            strategy_name=annual_result.strategy_name,
            rated_power_kw=float(annual_result.rated_power_kw),
            rated_energy_kwh=float(annual_result.rated_energy_kwh),
            project_life_years=int(project_life_years),
            discount_rate=float(discount_rate),
            capital_cost_breakdown=capex_breakdown,
            annual_revenue_audit=annual_audit,
            cashflow_table=cashflow_table,
            initial_investment_yuan=initial_investment_yuan,
            total_replacement_cost_yuan=total_replacement,
            total_salvage_value_yuan=total_salvage,
            npv_yuan=float(npv_yuan),
            irr=irr,
            simple_payback_years=simple_payback,
            discounted_payback_years=discounted_payback,
            annualized_net_cashflow_yuan=annualized_net_cashflow,
            lc_net_profit_yuan=lc_net_profit,
            metadata={
                "replacement_year_effective": self._resolve_replacement_year(ctx.strategy, ctx, annual_result),
                "replacement_cost_ratio_effective": self._resolve_replacement_cost_ratio(ctx.strategy, ctx),
                "cycle_life_efc_effective": self._resolve_cycle_life_efc(ctx.strategy, ctx),
                "replacement_trigger_soh_effective": self._resolve_replacement_soh_params(ctx)[0],
                "replacement_reset_soh_effective": self._resolve_replacement_soh_params(ctx)[1],
                "first_year_capacity_factor": float(cashflow_table.capacity_factor[0]) if len(cashflow_table.capacity_factor) else 1.0,
                "last_year_capacity_factor": float(cashflow_table.capacity_factor[-1]) if len(cashflow_table.capacity_factor) else 1.0,
                "gross_initial_investment_yuan": float(initial_investment_yuan),
                "government_subsidy_yuan": float(government_subsidy_yuan),
                "government_subsidy_rate_on_capex_effective": float(
                    max(0.0, _meta_float(meta, "government_subsidy_rate_on_capex", 0.0))
                ),
                "government_subsidy_yuan_per_kwh_effective": float(
                    max(0.0, _meta_float(meta, "government_subsidy_yuan_per_kwh", 0.0))
                ),
                "government_subsidy_yuan_per_kw_effective": float(
                    max(0.0, _meta_float(meta, "government_subsidy_yuan_per_kw", 0.0))
                ),
                "government_subsidy_cap_yuan_effective": float(
                    max(0.0, _meta_float(meta, "government_subsidy_cap_yuan", 0.0))
                ),
                "initial_net_investment_yuan": float(initial_net_investment_yuan),
                "annual_replacement_equivalent_cost_yuan": float(replacement_equivalent_annual),
                "annual_salvage_equivalent_value_yuan": float(salvage_equivalent_annual),
                "annual_net_cashflow_after_replacement_equivalent_yuan": float(
                    annual_net_cashflow_after_replacement_equivalent_yuan
                ),
            },
        )
        return result

    def _build_initial_capex_breakdown(
        self,
        ctx: AnnualOperationContext,
        rated_power_kw: float,
        rated_energy_kwh: float,
    ) -> CapitalCostBreakdown:
        strategy = ctx.strategy
        cfg = self.config
        meta = dict(ctx.meta)

        energy_capex = rated_energy_kwh * float(strategy.capex_energy_yuan_per_kwh)
        power_capex = rated_power_kw * float(strategy.capex_power_yuan_per_kw)

        power_related_override = _meta_float(meta, "power_related_capex_yuan_per_kw", 0.0)
        if power_related_override > 0 and power_capex <= 0:
            power_capex = rated_power_kw * power_related_override

        base_capex = energy_capex + power_capex

        if cfg.use_strategy_metadata_overrides:
            safety_ratio = self._extract_float(
                strategy.metadata, "safety_markup_ratio", cfg.default_safety_markup_ratio
            )
            integration_ratio = self._extract_float(
                strategy.metadata, "integration_markup_ratio", cfg.default_integration_markup_ratio
            )
            other_capex = self._extract_float(
                strategy.metadata, "other_capex_yuan", cfg.default_other_capex_yuan
            )
        else:
            safety_ratio = float(cfg.default_safety_markup_ratio)
            integration_ratio = float(cfg.default_integration_markup_ratio)
            other_capex = float(cfg.default_other_capex_yuan)

        if cfg.use_context_meta_overrides:
            safety_ratio = _meta_float(meta, "safety_markup_ratio", float(safety_ratio))
            integration_ratio = _meta_float(meta, "integration_markup_ratio", float(integration_ratio))
            other_capex = _meta_float(meta, "other_capex_yuan", float(other_capex))

        safety_markup = base_capex * float(max(0.0, safety_ratio))
        integration_markup = base_capex * float(max(0.0, integration_ratio))

        return CapitalCostBreakdown(
            energy_capex_yuan=float(energy_capex),
            power_capex_yuan=float(power_capex),
            safety_markup_yuan=float(safety_markup),
            integration_markup_yuan=float(integration_markup),
            other_capex_yuan=float(max(0.0, other_capex)),
        )

    def _build_lifecycle_cashflow_table(
        self,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult,
        annual_audit: AnnualRevenueAuditResult,
        initial_investment_yuan: float,
        project_life_years: int,
        include_replacement: bool,
    ) -> LifecycleCashflowTable:
        strategy = ctx.strategy
        cfg = self.config

        n = int(project_life_years)
        years = np.arange(1, n + 1, dtype=float)

        revenue = np.zeros(n, dtype=float)
        arbitrage_revenue = np.zeros(n, dtype=float)
        demand_saving = np.zeros(n, dtype=float)
        auxiliary_service_revenue = np.zeros(n, dtype=float)
        capacity_revenue = np.zeros(n, dtype=float)
        loss_reduction_revenue = np.zeros(n, dtype=float)
        service_penalty = np.zeros(n, dtype=float)
        degradation_cost = np.zeros(n, dtype=float)
        network_penalty = np.zeros(n, dtype=float)
        operating_revenue = np.zeros(n, dtype=float)
        operating_cost = np.zeros(n, dtype=float)
        om_cost = np.zeros(n, dtype=float)
        replacement_cost = np.zeros(n, dtype=float)
        salvage_value = np.zeros(n, dtype=float)
        net_cashflow = np.zeros(n, dtype=float)
        discounted_cashflow = np.zeros(n, dtype=float)
        battery_soh = np.ones(n, dtype=float)
        capacity_factor = np.ones(n, dtype=float)

        replacement_year = self._resolve_replacement_year(strategy, ctx, annual_result)
        explicit_replacement_year = self._resolve_explicit_replacement_year(strategy, ctx)
        replacement_cost_ratio = self._resolve_replacement_cost_ratio(strategy, ctx)
        discount_rate = self._resolve_discount_rate(ctx)
        annual_revenue_growth_rate = _meta_float(ctx.meta, "annual_revenue_growth_rate", float(cfg.annual_revenue_growth_rate))
        annual_om_growth_rate = _meta_float(ctx.meta, "annual_om_growth_rate", float(cfg.annual_om_growth_rate))
        trigger_soh, reset_soh = self._resolve_replacement_soh_params(ctx)
        annual_cycles = max(0.0, float(getattr(annual_result, "annual_equivalent_full_cycles", 0.0)))
        cycle_fade_per_year = self._cycle_fade_per_year(strategy, ctx, annual_cycles, trigger_soh)
        calendar_fade_per_year = self._calendar_fade_per_year(ctx)

        year1_om = float(annual_audit.annual_om_cost_yuan)
        year1_auxiliary_service_revenue = float(
            annual_audit.annual_service_capacity_revenue_yuan
            + annual_audit.annual_service_delivery_revenue_yuan
        )
        year1_network_penalty = float(
            annual_audit.annual_transformer_penalty_yuan
            + annual_audit.annual_voltage_penalty_yuan
        )

        years_since_replacement = 0
        soh_base = 1.0

        for i in range(n):
            year_no = i + 1
            revenue_growth = (1.0 + float(annual_revenue_growth_rate)) ** i
            soh = self._battery_soh_for_age(
                soh_base=soh_base,
                years_since_replacement=years_since_replacement,
                cycle_fade_per_year=cycle_fade_per_year,
                calendar_fade_per_year=calendar_fade_per_year,
            )

            periodic_replacement_due = (
                include_replacement
                and explicit_replacement_year is not None
                and explicit_replacement_year > 0
                and year_no > 1
                and year_no % int(explicit_replacement_year) == 0
                and year_no < n
            )
            soh_replacement_due = (
                include_replacement
                and years_since_replacement > 0
                and soh <= trigger_soh + 1e-9
                and year_no < n
            )
            if periodic_replacement_due or soh_replacement_due:
                replacement_cost[i] = float(initial_investment_yuan) * float(replacement_cost_ratio)
                soh_base = reset_soh
                years_since_replacement = 0
                soh = self._battery_soh_for_age(
                    soh_base=soh_base,
                    years_since_replacement=years_since_replacement,
                    cycle_fade_per_year=cycle_fade_per_year,
                    calendar_fade_per_year=calendar_fade_per_year,
                )

            battery_soh[i] = max(0.0, min(1.0, float(soh)))
            capacity_factor[i] = battery_soh[i]

            revenue_scale = revenue_growth * capacity_factor[i]
            arbitrage_revenue[i] = float(annual_audit.annual_arbitrage_revenue_yuan) * revenue_scale
            demand_saving[i] = float(annual_audit.annual_demand_saving_yuan) * revenue_scale
            auxiliary_service_revenue[i] = year1_auxiliary_service_revenue * revenue_scale
            capacity_revenue[i] = float(annual_audit.annual_capacity_revenue_yuan) * revenue_scale
            loss_reduction_revenue[i] = float(annual_audit.annual_loss_reduction_revenue_yuan) * revenue_scale
            service_penalty[i] = float(annual_audit.annual_service_penalty_yuan) * revenue_scale
            degradation_cost[i] = float(annual_audit.annual_degradation_cost_yuan) * revenue_scale
            network_penalty[i] = year1_network_penalty * revenue_scale
            operating_revenue[i] = (
                arbitrage_revenue[i]
                + demand_saving[i]
                + auxiliary_service_revenue[i]
                + capacity_revenue[i]
                + loss_reduction_revenue[i]
            )
            operating_cost[i] = service_penalty[i] + degradation_cost[i] + network_penalty[i]
            revenue[i] = operating_revenue[i] - operating_cost[i]
            om_cost[i] = year1_om * (1.0 + float(annual_om_growth_rate)) ** i

            if cfg.include_salvage_value and year_no == n:
                salvage_value[i] = float(initial_investment_yuan) * float(max(0.0, strategy.salvage_ratio))

            net_cashflow[i] = revenue[i] - om_cost[i] - replacement_cost[i] + salvage_value[i]
            discounted_cashflow[i] = net_cashflow[i] / (1.0 + float(discount_rate)) ** year_no
            years_since_replacement += 1

        return LifecycleCashflowTable(
            years=years,
            revenue_yuan=revenue,
            arbitrage_revenue_yuan=arbitrage_revenue,
            demand_saving_yuan=demand_saving,
            auxiliary_service_revenue_yuan=auxiliary_service_revenue,
            capacity_revenue_yuan=capacity_revenue,
            loss_reduction_revenue_yuan=loss_reduction_revenue,
            service_penalty_yuan=service_penalty,
            degradation_cost_yuan=degradation_cost,
            network_penalty_yuan=network_penalty,
            operating_revenue_yuan=operating_revenue,
            operating_cost_yuan=operating_cost,
            battery_soh=battery_soh,
            capacity_factor=capacity_factor,
            om_cost_yuan=om_cost,
            replacement_cost_yuan=replacement_cost,
            salvage_value_yuan=salvage_value,
            net_cashflow_yuan=net_cashflow,
            discounted_net_cashflow_yuan=discounted_cashflow,
        )

    @staticmethod
    def _compute_npv_from_cashflow_table(
        initial_investment_yuan: float,
        cashflow_table: LifecycleCashflowTable,
    ) -> float:
        discounted_operating = float(np.sum(cashflow_table.discounted_net_cashflow_yuan))
        return discounted_operating - float(initial_investment_yuan)

    @staticmethod
    def _compute_irr(
        initial_investment_yuan: float,
        annual_net_cashflows_yuan: np.ndarray,
        search_low: float,
        search_high: float,
        max_iter: int,
        tol: float,
    ) -> float | None:
        cashflows = np.concatenate(
            [[-float(initial_investment_yuan)], np.asarray(annual_net_cashflows_yuan, dtype=float)]
        )

        def npv(rate: float) -> float:
            total = 0.0
            for t, cf in enumerate(cashflows):
                total += cf / (1.0 + rate) ** t
            return total

        low = float(search_low)
        high = float(search_high)
        f_low = npv(low)
        f_high = npv(high)

        if np.isnan(f_low) or np.isnan(f_high):
            return None
        if f_low == 0:
            return low
        if f_high == 0:
            return high
        if f_low * f_high > 0:
            return None

        for _ in range(max_iter):
            mid = 0.5 * (low + high)
            f_mid = npv(mid)
            if abs(f_mid) <= tol:
                return float(mid)
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid

        return float(0.5 * (low + high))

    @staticmethod
    def _compute_payback_years(
        initial_investment_yuan: float,
        cashflows: np.ndarray,
    ) -> float | None:
        cashflows = np.asarray(cashflows, dtype=float).reshape(-1)
        cumulative = -float(initial_investment_yuan)

        for idx, cf in enumerate(cashflows, start=1):
            prev = cumulative
            cumulative += float(cf)
            if cumulative >= 0:
                if abs(cf) < 1e-12:
                    return float(idx)
                frac = max(0.0, min(1.0, (-prev) / float(cf)))
                return float((idx - 1) + frac)

        return None

    def _resolve_project_life_years(self, ctx: AnnualOperationContext) -> int:
        life = _meta_int(ctx.meta, "project_life_years", None)
        if life is None:
            life = _meta_int(ctx.meta, "lifetime_years", None)
        if life is not None and life > 0:
            return int(life)
        return int(self.config.project_life_years)

    def _resolve_discount_rate(self, ctx: AnnualOperationContext) -> float:
        rate = _meta_float(ctx.meta, "discount_rate", np.nan)
        if np.isfinite(rate) and rate >= 0:
            return float(rate)
        return float(self.config.discount_rate)

    def _resolve_replacement_year(
        self,
        strategy,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult | None = None,
    ) -> int | None:
        explicit = self._resolve_explicit_replacement_year(strategy, ctx)
        if explicit is not None:
            return int(explicit)
        return self._derive_replacement_year(strategy, ctx, annual_result)

    def _resolve_explicit_replacement_year(self, strategy, ctx: AnnualOperationContext) -> int | None:
        cfg = self.config
        override = _meta_int(ctx.meta, "replacement_year_override", None)
        if override is not None and override > 0:
            return int(override)
        if strategy.replacement_year is not None and int(strategy.replacement_year) > 0:
            return int(strategy.replacement_year)
        if cfg.default_replacement_year_if_missing is not None:
            val = int(cfg.default_replacement_year_if_missing)
            return val if val > 0 else None
        return None

    def _derive_replacement_year(
        self,
        strategy,
        ctx: AnnualOperationContext,
        annual_result: AnnualOperationResult | None,
    ) -> int | None:
        if annual_result is None:
            return None
        trigger_soh, _ = self._resolve_replacement_soh_params(ctx)
        annual_cycles = max(0.0, float(getattr(annual_result, "annual_equivalent_full_cycles", 0.0)))
        fade_per_year = (
            self._cycle_fade_per_year(strategy, ctx, annual_cycles, trigger_soh)
            + self._calendar_fade_per_year(ctx)
        )
        headroom = max(0.0, 1.0 - float(trigger_soh))
        if headroom <= 0 or fade_per_year <= 0:
            return None
        years = int(np.ceil(headroom / fade_per_year)) + 1
        return max(1, years)

    def _resolve_cycle_life_efc(self, strategy, ctx: AnnualOperationContext) -> float:
        meta = dict(ctx.meta)
        strategy_meta = getattr(strategy, "metadata", {}) if isinstance(getattr(strategy, "metadata", {}), dict) else {}
        values = (
            meta.get("cycle_life_efc"),
            meta.get("cycle_life"),
            getattr(strategy, "cycle_life_efc", None),
            strategy_meta.get("cycle_life_efc"),
            self.config.default_cycle_life_efc,
        )
        for value in values:
            parsed = _meta_float({"value": value}, "value", np.nan)
            if np.isfinite(parsed) and parsed > 0:
                return float(parsed)
        return 0.0

    def _resolve_replacement_soh_params(self, ctx: AnnualOperationContext) -> tuple[float, float]:
        trigger = _meta_float(ctx.meta, "replacement_trigger_soh", float(self.config.replacement_trigger_soh))
        reset = _meta_float(ctx.meta, "replacement_reset_soh", float(self.config.replacement_reset_soh))
        trigger = max(0.0, min(0.99, float(trigger)))
        reset = max(trigger + 1e-6, min(1.0, float(reset)))
        return float(trigger), float(reset)

    def _cycle_fade_per_year(
        self,
        strategy,
        ctx: AnnualOperationContext,
        annual_cycles: float,
        trigger_soh: float,
    ) -> float:
        cycle_life_efc = self._resolve_cycle_life_efc(strategy, ctx)
        if cycle_life_efc <= 0 or annual_cycles <= 0:
            return 0.0
        soh_drop_to_eol = max(0.0, 1.0 - float(trigger_soh))
        return float(soh_drop_to_eol * max(0.0, annual_cycles) / cycle_life_efc)

    def _calendar_fade_per_year(self, ctx: AnnualOperationContext) -> float:
        calendar_life = _meta_float(ctx.meta, "calendar_life_years", float(self.config.default_calendar_life_years))
        calendar_share = _meta_float(ctx.meta, "calendar_fade_share", float(self.config.default_calendar_fade_share))
        if calendar_life <= 0 or calendar_share <= 0:
            return 0.0
        return float(max(0.0, min(1.0, calendar_share)) / calendar_life)

    @staticmethod
    def _battery_soh_for_age(
        soh_base: float,
        years_since_replacement: int,
        cycle_fade_per_year: float,
        calendar_fade_per_year: float,
    ) -> float:
        fade = (float(cycle_fade_per_year) + float(calendar_fade_per_year)) * max(0, int(years_since_replacement))
        return float(max(0.0, min(1.0, float(soh_base) - fade)))

    def _resolve_replacement_cost_ratio(self, strategy, ctx: AnnualOperationContext) -> float:
        cfg = self.config
        base = float(cfg.replacement_cost_ratio)
        if cfg.use_strategy_metadata_overrides:
            base = float(
                max(
                    0.0,
                    self._extract_float(
                        strategy.metadata,
                        "replacement_cost_ratio",
                        base,
                    ),
                )
            )
        ratio = _meta_float(ctx.meta, "replacement_cost_ratio_of_battery_capex", np.nan)
        if np.isfinite(ratio):
            return float(max(0.0, ratio))
        return float(max(0.0, _meta_float(ctx.meta, "replacement_cost_ratio", base)))

    def _resolve_government_subsidy(
        self,
        ctx: AnnualOperationContext,
        rated_power_kw: float,
        rated_energy_kwh: float,
        initial_investment_yuan: float,
    ) -> float:
        if not bool(getattr(ctx, "include_government_subsidy", False)):
            return 0.0

        rate = 0.0
        per_kwh = 0.0
        per_kw = 0.0
        subsidy_cap = np.inf
        rate = _meta_float(ctx.meta, "government_subsidy_rate_on_capex", rate)
        per_kwh = _meta_float(ctx.meta, "government_subsidy_yuan_per_kwh", per_kwh)
        per_kw = _meta_float(ctx.meta, "government_subsidy_yuan_per_kw", per_kw)
        subsidy_cap = _meta_float(ctx.meta, "government_subsidy_cap_yuan", subsidy_cap if np.isfinite(subsidy_cap) else 0.0)
        if subsidy_cap <= 0:
            subsidy_cap = np.inf

        subsidy = (
            float(initial_investment_yuan) * max(0.0, rate)
            + float(rated_energy_kwh) * max(0.0, per_kwh)
            + float(rated_power_kw) * max(0.0, per_kw)
        )
        return float(min(max(0.0, subsidy), subsidy_cap))

    @staticmethod
    def _extract_float(meta: dict[str, Any] | None, key: str, default: float) -> float:
        if not meta:
            return float(default)
        try:
            value = meta.get(key, default)
            if value is None:
                return float(default)
            return float(value)
        except Exception:
            return float(default)
