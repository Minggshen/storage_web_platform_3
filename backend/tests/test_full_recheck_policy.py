from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from storage_engine_project.main import _ensure_topk_full_recheck
from storage_engine_project.optimization.lemming_optimizer import LemmingOptimizationRunResult
from storage_engine_project.optimization.optimization_models import (
    ConstraintVector,
    FitnessEvaluationResult,
    ObjectiveVector,
    ScreeningResult,
    StorageDecision,
)


def _result(strategy_id: str, power_kw: float, npv_yuan: float, *, rechecked: bool = False) -> FitnessEvaluationResult:
    return FitnessEvaluationResult(
        decision=StorageDecision(
            strategy_id=strategy_id,
            rated_power_kw=power_kw,
            rated_energy_kwh=power_kw * 2.0,
        ),
        screening_result=ScreeningResult(is_feasible=True),
        objective_vector=ObjectiveVector(
            obj_npv=-npv_yuan,
            obj_payback=5.0,
            obj_investment=power_kw * 1000.0,
            obj_safety=0.0,
        ),
        constraint_vector=ConstraintVector(),
        annual_operation_result=SimpleNamespace(evaluation_mode="full_recheck") if rechecked else None,
        metadata={"recheck_performed": True} if rechecked else {},
    )


class _FakeEvaluator:
    def __init__(self) -> None:
        self.calls: list[StorageDecision] = []

    def evaluate_decision(
        self,
        *,
        ctx: Any,
        decision: StorageDecision,
        network_oracle: Any = None,
        force_full_recheck: bool = False,
    ) -> FitnessEvaluationResult:
        del ctx, network_oracle
        assert force_full_recheck is True
        self.calls.append(decision)
        return _result(decision.strategy_id, decision.rated_power_kw, npv_yuan=10_000.0 + decision.rated_power_kw, rechecked=True)


def test_final_best_is_selected_from_full_recheck_pool() -> None:
    archive = [
        _result("a", 100.0, 1000.0),
        _result("b", 200.0, 2000.0),
        _result("c", 300.0, 3000.0),
    ]
    run_result = LemmingOptimizationRunResult(
        archive_results=archive,
        population_results=list(archive),
        history=[],
        best_result=archive[-1],
        all_evaluation_count=len(archive),
    )
    evaluator = _FakeEvaluator()

    diagnostics = _ensure_topk_full_recheck(
        evaluator=evaluator,  # type: ignore[arg-type]
        opt_case=SimpleNamespace(context=object()),
        run_result=run_result,
        network_oracle=None,
        k=1,
        candidate_limit=2,
        per_strategy_limit=0,
        closure_max_rounds=0,
    )

    assert diagnostics["candidate_total"] == 2
    assert diagnostics["closure_recheck_rounds"] == 0
    assert diagnostics["final_selection_scope"] == "full_recheck_pool"
    assert len(evaluator.calls) == 2
    assert run_result.best_result is not None
    assert run_result.best_result.metadata["recheck_performed"] is True
    assert run_result.best_result.annual_operation_result is not None
