from __future__ import annotations

"""
兼容入口：把你原工程里 simulation.dispatch_solver 的调用，
切换到第二层 DayAheadScheduler。

推荐使用：
    solve_daily_dispatch(...)
"""

from dataclasses import dataclass
from typing import Any

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.simulation.day_ahead_scheduler import (
    DayAheadScheduler,
    DayAheadSchedulerConfig,
)
from storage_engine_project.simulation.dispatch_result_models import DayAheadDispatchPlan


@dataclass(slots=True)
class DailyDispatchInput:
    ctx: AnnualOperationContext
    day_index: int
    rated_power_kw: float
    rated_energy_kwh: float
    initial_soc: float
    target_terminal_soc: float | None = None


class DailyDispatchSolver:
    def __init__(self, config: DayAheadSchedulerConfig | None = None) -> None:
        self.scheduler = DayAheadScheduler(config=config)

    def solve(self, dispatch_input: DailyDispatchInput) -> DayAheadDispatchPlan:
        return self.scheduler.schedule_day(
            ctx=dispatch_input.ctx,
            day_index=dispatch_input.day_index,
            rated_power_kw=dispatch_input.rated_power_kw,
            rated_energy_kwh=dispatch_input.rated_energy_kwh,
            initial_soc=dispatch_input.initial_soc,
            target_terminal_soc=dispatch_input.target_terminal_soc,
        )


def solve_daily_dispatch(
    ctx: AnnualOperationContext,
    day_index: int,
    rated_power_kw: float,
    rated_energy_kwh: float,
    initial_soc: float,
    target_terminal_soc: float | None = None,
    config: DayAheadSchedulerConfig | None = None,
) -> DayAheadDispatchPlan:
    solver = DailyDispatchSolver(config=config)
    return solver.solve(
        DailyDispatchInput(
            ctx=ctx,
            day_index=day_index,
            rated_power_kw=rated_power_kw,
            rated_energy_kwh=rated_energy_kwh,
            initial_soc=initial_soc,
            target_terminal_soc=target_terminal_soc,
        )
    )