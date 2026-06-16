from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.data.context_factory import _apply_frontend_economic_overrides
from storage_engine_project.data.service_loader import ServiceCalendar
from storage_engine_project.data.storage_strategy_loader import StorageStrategy
from storage_engine_project.economics.lifecycle_financial_evaluator import LifecycleFinancialEvaluator
from storage_engine_project.economics.service_revenue_evaluator import AnnualRevenueAuditor


def _service_calendar() -> ServiceCalendar:
    zeros = np.zeros((365, 24), dtype=float)
    return ServiceCalendar(
        scenario_name="test",
        availability_matrix=zeros,
        capacity_price_matrix_yuan_per_kw=zeros,
        delivery_price_matrix_yuan_per_kwh=zeros,
        penalty_price_matrix_yuan_per_kwh=zeros,
        activation_factor_matrix=zeros,
    )


def _context(strategy: StorageStrategy, meta: dict[str, object]) -> AnnualOperationContext:
    zeros = np.zeros((365, 24), dtype=float)
    return AnnualOperationContext(
        internal_model_id="load_01",
        strategy=strategy,
        strategy_library={strategy.strategy_id: strategy},
        load_matrix_kw=zeros,
        tariff_matrix_yuan_per_kwh=zeros,
        pv_matrix_kw=zeros,
        service_calendar=_service_calendar(),
        meta=meta,
    )


def test_registry_device_fields_do_not_override_strategy_library_values() -> None:
    strategy = StorageStrategy(
        strategy_id="device_a",
        strategy_name="Device A",
        cycle_life_efc=5000,
        annual_cycle_limit=320,
        degradation_cost_yuan_per_kwh_throughput=0.02,
        capex_energy_yuan_per_kwh=900,
    )
    ctx = _context(
        strategy,
        {
            "cycle_life_efc": 9000,
            "annual_cycle_limit": 999,
            "degradation_cost_yuan_per_kwh_throughput": 0.99,
            "battery_capex_share": 0.6,
        },
    )

    updated = _apply_frontend_economic_overrides(ctx)

    assert updated.strategy.cycle_life_efc == 5000
    assert updated.strategy.annual_cycle_limit == 320
    assert updated.strategy.degradation_cost_yuan_per_kwh_throughput == 0.02
    assert LifecycleFinancialEvaluator()._resolve_cycle_life_efc(updated.strategy, updated) == 5000


def test_missing_degradation_cost_is_derived_from_device_price_and_life() -> None:
    strategy = StorageStrategy(
        strategy_id="device_b",
        strategy_name="Device B",
        cycle_life_efc=6000,
        degradation_cost_yuan_per_kwh_throughput=0.0,
        capex_energy_yuan_per_kwh=1000,
    )
    ctx = _context(strategy, {"cycle_life_efc": 12000, "battery_capex_share": 0.6})

    updated = _apply_frontend_economic_overrides(ctx)

    assert updated.strategy.degradation_cost_yuan_per_kwh_throughput == 0.05


def test_annual_om_cost_uses_device_library_ratio_by_default() -> None:
    strategy = StorageStrategy(
        strategy_id="device_c",
        strategy_name="Device C",
        om_ratio_annual=0.03,
    )
    ctx = _context(
        strategy,
        {
            "annual_fixed_om_yuan_per_kw_year": 999,
            "annual_variable_om_yuan_per_kwh": 999,
        },
    )
    annual_result = SimpleNamespace(
        internal_model_id="load_01",
        strategy_id="device_c",
        strategy_name="Device C",
        rated_power_kw=100.0,
        rated_energy_kwh=200.0,
        effective_power_cap_kw=100.0,
        annual_arbitrage_revenue_yuan=0.0,
        annual_service_capacity_revenue_yuan=0.0,
        annual_service_delivery_revenue_yuan=0.0,
        annual_service_penalty_yuan=0.0,
        annual_degradation_cost_yuan=0.0,
        annual_transformer_penalty_yuan=0.0,
        annual_voltage_penalty_yuan=0.0,
        annual_demand_saving_yuan=0.0,
        annual_net_operating_cashflow_yuan=0.0,
        annual_battery_throughput_kwh=1000.0,
        annual_equivalent_full_cycles=5.0,
        transformer_violation_hours=0.0,
        max_transformer_slack_kw=0.0,
        metadata={},
        monthly_summary_dataframe=lambda: pd.DataFrame(),
    )

    audit = AnnualRevenueAuditor().evaluate(ctx, annual_result, initial_capex_yuan=100000.0)

    assert audit.annual_om_cost_yuan == 3000.0
    assert audit.metadata["annual_om_cost_method"] == "strategy_om_ratio"
