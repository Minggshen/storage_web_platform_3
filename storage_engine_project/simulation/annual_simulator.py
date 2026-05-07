from __future__ import annotations

"""
兼容入口：把你原工程里 simulation.annual_simulator 的调用，
切换到第三层 AnnualOperationKernel。

推荐使用：
    run_annual_simulation(...)
"""

from dataclasses import dataclass
import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.simulation.annual_operation_kernel import (
    AnnualOperationKernel,
    AnnualOperationKernelConfig,
    AnnualOperationResult,
)
from storage_engine_project.simulation.network_constraint_oracle import NetworkConstraintOracle


@dataclass(slots=True)
class AnnualSimulationInput:
    ctx: AnnualOperationContext
    rated_power_kw: float
    rated_energy_kwh: float
    actual_load_matrix_kw: np.ndarray | None = None
    actual_pv_matrix_kw: np.ndarray | None = None
    network_oracle: NetworkConstraintOracle | None = None


class AnnualSimulator:
    def __init__(self, config: AnnualOperationKernelConfig | None = None) -> None:
        self.kernel = AnnualOperationKernel(config=config)

    def run(self, sim_input: AnnualSimulationInput) -> AnnualOperationResult:
        return self.kernel.run_year(
            ctx=sim_input.ctx,
            rated_power_kw=sim_input.rated_power_kw,
            rated_energy_kwh=sim_input.rated_energy_kwh,
            actual_load_matrix_kw=sim_input.actual_load_matrix_kw,
            actual_pv_matrix_kw=sim_input.actual_pv_matrix_kw,
            network_oracle=sim_input.network_oracle,
        )


def run_annual_simulation(
    ctx: AnnualOperationContext,
    rated_power_kw: float,
    rated_energy_kwh: float,
    actual_load_matrix_kw: np.ndarray | None = None,
    actual_pv_matrix_kw: np.ndarray | None = None,
    network_oracle: NetworkConstraintOracle | None = None,
    config: AnnualOperationKernelConfig | None = None,
) -> AnnualOperationResult:
    simulator = AnnualSimulator(config=config)
    return simulator.run(
        AnnualSimulationInput(
            ctx=ctx,
            rated_power_kw=rated_power_kw,
            rated_energy_kwh=rated_energy_kwh,
            actual_load_matrix_kw=actual_load_matrix_kw,
            actual_pv_matrix_kw=actual_pv_matrix_kw,
            network_oracle=network_oracle,
        )
    )