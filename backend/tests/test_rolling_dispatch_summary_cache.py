from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np

from storage_engine_project.simulation.dispatch_result_models import (
    DayAheadDispatchPlan,
    DayAheadObjectiveBreakdown,
)
from storage_engine_project.simulation.network_constraint_oracle import HourlyNetworkConstraint
from storage_engine_project.simulation.rolling_dispatch import RollingDispatchController


class _RecordingOracle:
    def __init__(self) -> None:
        self.plan_summary_ids: list[int] = []

    def get_hour_constraint(
        self,
        *,
        ctx: Any,
        day_index: int,
        hour_index: int,
        actual_net_load_kw: float,
        planned_charge_kw: float,
        planned_discharge_kw: float,
        planned_service_kw: float,
        rated_power_kw: float,
        rated_energy_kwh: float,
        effective_power_cap_kw: float,
        current_soc: float,
        extra: dict[str, Any] | None = None,
    ) -> HourlyNetworkConstraint:
        del (
            ctx,
            day_index,
            hour_index,
            actual_net_load_kw,
            planned_charge_kw,
            planned_discharge_kw,
            planned_service_kw,
            rated_power_kw,
            rated_energy_kwh,
            current_soc,
        )
        self.plan_summary_ids.append(id((extra or {})["plan_summary"]))
        return HourlyNetworkConstraint(
            max_charge_kw=effective_power_cap_kw,
            max_discharge_kw=effective_power_cap_kw,
            service_power_cap_kw=effective_power_cap_kw,
        )


def _build_context() -> SimpleNamespace:
    return SimpleNamespace(
        internal_model_id="case_a",
        strategy=SimpleNamespace(
            strategy_id="strategy_a",
            eta_charge=0.95,
            eta_discharge=0.95,
            degradation_cost_yuan_per_kwh_throughput=0.0,
        ),
        operation_config=SimpleNamespace(
            daily_terminal_soc_tolerance=0.02,
            enable_terminal_soc_correction=False,
        ),
        service_config=SimpleNamespace(delivery_score_floor=1.0),
    )


def _build_zero_plan() -> DayAheadDispatchPlan:
    zeros = np.zeros(24, dtype=float)
    return DayAheadDispatchPlan(
        day_index=0,
        internal_model_id="case_a",
        strategy_id="strategy_a",
        strategy_name="Strategy A",
        rated_power_kw=100.0,
        rated_energy_kwh=200.0,
        effective_power_cap_kw=100.0,
        soc_min=0.1,
        soc_max=0.9,
        initial_soc=0.5,
        target_terminal_soc=None,
        final_soc=0.5,
        hour_count=24,
        load_kw=zeros,
        pv_kw=zeros,
        net_load_kw=zeros,
        tariff_yuan_per_kwh=zeros,
        service_availability=zeros,
        service_activation_factor=zeros,
        service_capacity_price_yuan_per_kw=zeros,
        service_delivery_price_yuan_per_kwh=zeros,
        service_penalty_price_yuan_per_kwh=zeros,
        charge_kw=zeros,
        discharge_kw=zeros,
        service_commit_kw=zeros,
        soc_path=np.full(25, 0.5, dtype=float),
        grid_exchange_kw=zeros,
        transformer_slack_kw=zeros,
        objective_breakdown=DayAheadObjectiveBreakdown(),
        solver_status="test",
    )


def test_execute_day_reuses_single_plan_summary_for_hourly_oracle_calls(monkeypatch) -> None:
    original_summary_dict = DayAheadDispatchPlan.summary_dict
    call_count = 0

    def counted_summary_dict(self: DayAheadDispatchPlan) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return original_summary_dict(self)

    monkeypatch.setattr(DayAheadDispatchPlan, "summary_dict", counted_summary_dict)
    oracle = _RecordingOracle()

    result = RollingDispatchController().execute_day(
        ctx=_build_context(),  # type: ignore[arg-type]
        plan=_build_zero_plan(),
        network_oracle=oracle,  # type: ignore[arg-type]
    )

    assert result.hour_count == 24
    assert call_count == 1
    assert len(oracle.plan_summary_ids) == 24
    assert len(set(oracle.plan_summary_ids)) == 1


def test_recompute_does_not_reuse_saved_constraint_when_soc_changes() -> None:
    oracle = _RecordingOracle()
    controller = RollingDispatchController()
    plan = _build_zero_plan()
    saved_constraints = [
        HourlyNetworkConstraint(
            max_charge_kw=plan.effective_power_cap_kw,
            max_discharge_kw=plan.effective_power_cap_kw,
            service_power_cap_kw=plan.effective_power_cap_kw,
        )
        for _ in range(24)
    ]

    controller._recompute(
        ctx=_build_context(),
        plan=plan,
        oracle=oracle,
        actual_net=np.zeros(24, dtype=float),
        tariff=np.zeros(24, dtype=float),
        activation=np.zeros(24, dtype=float),
        cap_price=np.zeros(24, dtype=float),
        del_price=np.zeros(24, dtype=float),
        pen_price=np.zeros(24, dtype=float),
        expected_penalty_ratio=0.0,
        pch_exec=np.zeros(24, dtype=float),
        pdis_exec=np.zeros(24, dtype=float),
        psrv_exec=np.zeros(24, dtype=float),
        saved_constraints=saved_constraints,
        saved_constraint_soc=[0.0] * 24,
        plan_summary=plan.summary_dict(),
    )

    assert len(oracle.plan_summary_ids) == 24
