from __future__ import annotations

"""
兼容入口：把你原工程 optimization.fitness_evaluator 的调用，
切换到第五层 StorageFitnessEvaluator。

推荐使用：
    evaluate_candidate(...)
"""

from dataclasses import dataclass
import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.optimization.optimization_models import FitnessEvaluationResult, StorageDecision
from storage_engine_project.optimization.storage_fitness_evaluator import (
    FitnessEvaluatorConfig,
    StorageFitnessEvaluator,
)
from storage_engine_project.simulation.network_constraint_oracle import NetworkConstraintOracle


@dataclass(slots=True)
class CandidateEvaluationInput:
    ctx: AnnualOperationContext
    decision: StorageDecision
    actual_load_matrix_kw: np.ndarray | None = None
    actual_pv_matrix_kw: np.ndarray | None = None
    network_oracle: NetworkConstraintOracle | None = None


class FitnessEvaluator:
    def __init__(self, config: FitnessEvaluatorConfig | None = None) -> None:
        self.evaluator = StorageFitnessEvaluator(config=config)

    def evaluate(self, eval_input: CandidateEvaluationInput) -> FitnessEvaluationResult:
        return self.evaluator.evaluate_decision(
            ctx=eval_input.ctx,
            decision=eval_input.decision,
            actual_load_matrix_kw=eval_input.actual_load_matrix_kw,
            actual_pv_matrix_kw=eval_input.actual_pv_matrix_kw,
            network_oracle=eval_input.network_oracle,
        )


def evaluate_candidate(
    ctx: AnnualOperationContext,
    strategy_id: str,
    rated_power_kw: float,
    rated_energy_kwh: float,
    actual_load_matrix_kw: np.ndarray | None = None,
    actual_pv_matrix_kw: np.ndarray | None = None,
    network_oracle: NetworkConstraintOracle | None = None,
    config: FitnessEvaluatorConfig | None = None,
) -> FitnessEvaluationResult:
    evaluator = FitnessEvaluator(config=config)
    return evaluator.evaluate(
        CandidateEvaluationInput(
            ctx=ctx,
            decision=StorageDecision(
                strategy_id=strategy_id,
                rated_power_kw=rated_power_kw,
                rated_energy_kwh=rated_energy_kwh,
            ),
            actual_load_matrix_kw=actual_load_matrix_kw,
            actual_pv_matrix_kw=actual_pv_matrix_kw,
            network_oracle=network_oracle,
        )
    )