from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from storage_engine_project.optimization.lemming_optimizer import (
    LemmingOptimizationRunResult,
    LemmingOptimizer,
    LemmingOptimizerConfig,
)
from storage_engine_project.optimization.optimization_models import (
    ConstraintVector,
    FitnessEvaluationResult,
    ObjectiveVector,
    ScreeningResult,
    StorageDecision,
)
from storage_engine_project.optimization.optimizer_bridge import OptimizerBridge, SearchSpaceConfig
from storage_engine_project.optimization.per_strategy_orchestrator import (
    PerStrategyOrchestratorConfig,
    _merge_run_results,
    run_per_strategy_ga,
)


class _EvaluatorConfig:
    full_recheck_for_fast_feasible_only = True


class _FakeEvaluator:
    def __init__(self) -> None:
        self.config = _EvaluatorConfig()
        self.calls: list[tuple[StorageDecision, object | None, bool]] = []

    def evaluate_decision(
        self,
        *,
        ctx: Any,
        decision: StorageDecision,
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: Any = None,
    ) -> FitnessEvaluationResult:
        del ctx, actual_load_matrix_kw, actual_pv_matrix_kw
        self.calls.append((decision, network_oracle, self.config.full_recheck_for_fast_feasible_only))
        return _result(
            strategy_id=decision.strategy_id,
            power_kw=decision.rated_power_kw,
            duration_h=decision.duration_h(),
            npv_yuan=decision.rated_power_kw,
            payback_years=max(1.0, decision.duration_h()),
            investment_yuan=decision.rated_energy_kwh,
            device_safety_cost=0.2 if decision.strategy_id == "safe" else 0.8,
        )


def _space() -> SearchSpaceConfig:
    return SearchSpaceConfig(
        power_min_kw=50.0,
        power_max_kw=500.0,
        duration_min_h=1.0,
        duration_max_h=4.0,
    )


def _bridge(strategy_id: str = "strategy_a") -> OptimizerBridge:
    return OptimizerBridge(
        evaluator=_FakeEvaluator(),  # type: ignore[arg-type]
        fixed_strategy_id=strategy_id,
        search_space_config=_space(),
    )


def _result(
    *,
    strategy_id: str,
    power_kw: float,
    duration_h: float,
    npv_yuan: float,
    payback_years: float,
    investment_yuan: float,
    device_safety_cost: float | None = None,
    feasible: bool = True,
) -> FitnessEvaluationResult:
    metadata: dict[str, Any] = {}
    if device_safety_cost is not None:
        metadata = {
            "device_safety_available": True,
            "device_safety_cost": float(device_safety_cost),
        }
    return FitnessEvaluationResult(
        decision=StorageDecision(
            strategy_id=strategy_id,
            rated_power_kw=power_kw,
            rated_energy_kwh=power_kw * duration_h,
        ),
        screening_result=ScreeningResult(is_feasible=feasible),
        objective_vector=ObjectiveVector(
            obj_npv=-npv_yuan,
            obj_payback=payback_years,
            obj_investment=investment_yuan,
            obj_safety=0.0,
        ),
        constraint_vector=ConstraintVector(),
        metadata=metadata,
    )


def test_vector_to_decision_2d() -> None:
    decision = _bridge("fixed").vector_to_decision(np.array([150.0, 2.5]))

    assert decision.strategy_id == "fixed"
    assert decision.rated_power_kw == pytest.approx(150.0)
    assert decision.rated_energy_kwh == pytest.approx(375.0)


def test_decision_to_vector_2d() -> None:
    bridge = _bridge("fixed")
    vector = bridge.decision_to_vector(StorageDecision("fixed", 150.0, 375.0))

    assert vector.tolist() == pytest.approx([150.0, 2.5])
    with pytest.raises(KeyError):
        bridge.decision_to_vector(StorageDecision("other", 150.0, 375.0))


def test_bounds_2d() -> None:
    lb, ub = _bridge().get_global_bounds()

    assert lb.tolist() == pytest.approx([50.0, 1.0])
    assert ub.tolist() == pytest.approx([500.0, 4.0])


def test_crossover_2d() -> None:
    optimizer = LemmingOptimizer(
        bridge=_bridge(),
        config=LemmingOptimizerConfig(random_seed=42, verbose=False),
    )

    child = optimizer._crossover(np.array([100.0, 2.0]), np.array([200.0, 4.0]))

    assert child.shape == (2,)
    assert 100.0 < child[0] < 200.0
    assert 2.0 < child[1] < 4.0


def test_mutate_2d() -> None:
    optimizer = LemmingOptimizer(
        bridge=_bridge(),
        config=LemmingOptimizerConfig(random_seed=42, mutation_rate=1.0, verbose=False),
    )

    mutated = optimizer._mutate(np.array([100.0, 2.0]))

    assert mutated.shape == (2,)
    assert mutated[0] != pytest.approx(100.0)
    assert mutated[1] != pytest.approx(2.0)


def test_orchestrator_merge_keeps_device_safe_candidate_without_update_archive_pruning() -> None:
    economic_strong = _result(
        strategy_id="economic",
        power_kw=100.0,
        duration_h=2.0,
        npv_yuan=1000.0,
        payback_years=1.0,
        investment_yuan=100.0,
        device_safety_cost=1.0,
    )
    safer_but_objective_dominated = _result(
        strategy_id="safe",
        power_kw=100.0,
        duration_h=2.0,
        npv_yuan=900.0,
        payback_years=1.5,
        investment_yuan=120.0,
        device_safety_cost=0.0,
    )
    merged = _merge_run_results(
        [
            (0, "economic", LemmingOptimizationRunResult([economic_strong], [economic_strong], [], economic_strong, 1)),
            (1, "safe", LemmingOptimizationRunResult([safer_but_objective_dominated], [safer_but_objective_dominated], [], safer_but_objective_dominated, 1)),
        ],
        config=PerStrategyOrchestratorConfig(safety_economy_tradeoff=1.0),
    )

    assert {result.decision.strategy_id for result in merged.archive_results} == {"economic", "safe"}
    assert merged.best_result is safer_but_objective_dominated


def test_seed_per_strategy_and_no_network_oracle_during_search() -> None:
    evaluator = _FakeEvaluator()
    run_per_strategy_ga(
        evaluator=evaluator,
        ctx=object(),  # type: ignore[arg-type]
        strategy_ids=["a", "b"],
        search_spaces={"a": _space(), "b": _space()},
        config=PerStrategyOrchestratorConfig(
            optimizer_config=LemmingOptimizerConfig(
                population_size=4,
                generations=1,
                random_seed=7,
                verbose=False,
            ),
            generations_per_strategy=1,
        ),
        network_oracle=object(),
    )

    a_points = {
        (round(call[0].rated_power_kw, 6), round(call[0].duration_h(), 6))
        for call in evaluator.calls
        if call[0].strategy_id == "a"
    }
    b_points = {
        (round(call[0].rated_power_kw, 6), round(call[0].duration_h(), 6))
        for call in evaluator.calls
        if call[0].strategy_id == "b"
    }
    assert a_points != b_points
    assert all(call[1] is None for call in evaluator.calls)
    assert all(call[2] is False for call in evaluator.calls)
    assert evaluator.config.full_recheck_for_fast_feasible_only is True


def test_history_merge_metadata_and_global_generation() -> None:
    result = _result(
        strategy_id="a",
        power_kw=100.0,
        duration_h=2.0,
        npv_yuan=100.0,
        payback_years=2.0,
        investment_yuan=200.0,
    )
    merged = _merge_run_results(
        [
            (0, "a", LemmingOptimizationRunResult([result], [result], [{"generation": 1}], result, 1)),
            (1, "b", LemmingOptimizationRunResult([result], [result], [{"generation": 2}], result, 1)),
        ],
        config=PerStrategyOrchestratorConfig(generations_per_strategy=3),
    )

    assert merged.history[0]["generation"] == 1
    assert merged.history[0]["global_generation"] == 1
    assert merged.history[0]["local_generation"] == 1
    assert merged.history[0]["strategy_id"] == "a"
    assert merged.history[1]["generation"] == 5
    assert merged.history[1]["global_generation"] == 5
    assert merged.history[1]["local_generation"] == 2
    assert merged.history[1]["strategy_index"] == 1


def test_global_progress_mapping() -> None:
    events: list[dict[str, Any]] = []
    run_per_strategy_ga(
        evaluator=_FakeEvaluator(),
        ctx=object(),  # type: ignore[arg-type]
        strategy_ids=["a", "b"],
        search_spaces={"a": _space(), "b": _space()},
        config=PerStrategyOrchestratorConfig(
            optimizer_config=LemmingOptimizerConfig(
                population_size=1,
                generations=2,
                random_seed=3,
                verbose=False,
            ),
            generations_per_strategy=2,
        ),
        progress_callback=events.append,
    )

    generation_starts = [event for event in events if event.get("event") == "ga_generation_start"]
    assert [event["generation"] for event in generation_starts] == [1, 2, 3, 4]
    assert all(event["generations"] == 4 for event in generation_starts)
