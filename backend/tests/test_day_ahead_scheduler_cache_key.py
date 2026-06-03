from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from storage_engine_project.data.storage_strategy_loader import StorageStrategy
from storage_engine_project.simulation.day_ahead_scheduler import DayAheadScheduler
from storage_engine_project.simulation.service_headroom import DailyServiceProfile


class _CacheKeyContext:
    def __init__(self, *, transformer_capacity_kva: float | None = 1000.0) -> None:
        self.internal_model_id = "case_a"
        self.transformer_capacity_kva = transformer_capacity_kva
        self.transformer_pf_limit = 0.95
        self.transformer_reserve_ratio = 0.1
        self.strategy = StorageStrategy(
            strategy_id="strategy_a",
            strategy_name="Strategy A",
            eta_charge=0.95,
            eta_discharge=0.95,
            degradation_cost_yuan_per_kwh_throughput=0.01,
        )
        self.operation_config = SimpleNamespace(
            enable_transformer_limit=True,
            enforce_daily_terminal_soc=True,
            daily_terminal_soc_tolerance=0.02,
        )

    @property
    def transformer_active_power_limit_kw(self) -> float | None:
        if self.transformer_capacity_kva is None:
            return None
        return (
            float(self.transformer_capacity_kva)
            * float(self.transformer_pf_limit)
            * max(0.0, 1.0 - float(self.transformer_reserve_ratio))
        )


def _service_profile(capacity_price: float = 1.0) -> DailyServiceProfile:
    ones = np.ones(24, dtype=float)
    zeros = np.zeros(24, dtype=float)
    return DailyServiceProfile(
        enabled=True,
        availability=ones,
        capacity_price_yuan_per_kw=np.full(24, capacity_price, dtype=float),
        delivery_price_yuan_per_kwh=zeros,
        penalty_price_yuan_per_kwh=zeros,
        activation_factor=ones * 0.2,
        max_service_power_kw=50.0,
        headroom_ratio=0.1,
        expected_penalty_ratio=0.0,
    )


def test_day_ahead_cache_key_includes_transformer_limit_and_service_prices() -> None:
    scheduler = DayAheadScheduler()
    load = np.full(24, 100.0, dtype=float)
    pv = np.zeros(24, dtype=float)
    tariff = np.full(24, 0.7, dtype=float)

    base_key = scheduler._build_cache_key(
        ctx=_CacheKeyContext(transformer_capacity_kva=1000.0),  # type: ignore[arg-type]
        rated_power_kw=100.0,
        rated_energy_kwh=200.0,
        effective_power_cap_kw=95.0,
        initial_soc=0.5,
        terminal_soc_target=0.5,
        soc_min=0.1,
        soc_max=0.9,
        load_kw=load,
        pv_kw=pv,
        tariff=tariff,
        svc_profile=_service_profile(capacity_price=1.0),
    )
    changed_transformer_key = scheduler._build_cache_key(
        ctx=_CacheKeyContext(transformer_capacity_kva=500.0),  # type: ignore[arg-type]
        rated_power_kw=100.0,
        rated_energy_kwh=200.0,
        effective_power_cap_kw=95.0,
        initial_soc=0.5,
        terminal_soc_target=0.5,
        soc_min=0.1,
        soc_max=0.9,
        load_kw=load,
        pv_kw=pv,
        tariff=tariff,
        svc_profile=_service_profile(capacity_price=1.0),
    )
    changed_service_price_key = scheduler._build_cache_key(
        ctx=_CacheKeyContext(transformer_capacity_kva=1000.0),  # type: ignore[arg-type]
        rated_power_kw=100.0,
        rated_energy_kwh=200.0,
        effective_power_cap_kw=95.0,
        initial_soc=0.5,
        terminal_soc_target=0.5,
        soc_min=0.1,
        soc_max=0.9,
        load_kw=load,
        pv_kw=pv,
        tariff=tariff,
        svc_profile=_service_profile(capacity_price=2.0),
    )

    assert base_key != changed_transformer_key
    assert base_key != changed_service_price_key
