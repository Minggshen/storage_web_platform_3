from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from storage_engine_project.optimization.lemming_optimizer import (
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
from storage_engine_project.optimization.optimizer_bridge import (
    DecisionCacheKey,
    OptimizerBridge,
    SearchSpaceConfig,
)
from storage_engine_project.optimization.objective_scoring import compute_weighted_objective_scores
from storage_engine_project.optimization.pareto_utils import select_best_compromise


class _CountingEvaluator:
    def __init__(self) -> None:
        self.calls: list[StorageDecision] = []

    def evaluate_decision(
        self,
        *,
        ctx: Any,
        decision: StorageDecision,
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: Any = None,
    ) -> FitnessEvaluationResult:
        del ctx, actual_load_matrix_kw, actual_pv_matrix_kw, network_oracle
        self.calls.append(decision)
        return FitnessEvaluationResult(
            decision=decision,
            screening_result=ScreeningResult(is_feasible=True),
            objective_vector=ObjectiveVector(
                obj_npv=-decision.rated_power_kw,
                obj_payback=decision.duration_h(),
                obj_investment=decision.rated_energy_kwh,
                obj_safety=0.0,
            ),
            constraint_vector=ConstraintVector(),
        )


def _rankable_result(
    *,
    label: str,
    npv_yuan: float,
    payback_years: float,
    investment_yuan: float,
    obj_safety: float = 0.0,
) -> FitnessEvaluationResult:
    return FitnessEvaluationResult(
        decision=StorageDecision(
            strategy_id=label,
            rated_power_kw=100.0,
            rated_energy_kwh=200.0,
        ),
        screening_result=ScreeningResult(is_feasible=True),
        objective_vector=ObjectiveVector(
            obj_npv=-npv_yuan,
            obj_payback=payback_years,
            obj_investment=investment_yuan,
            obj_safety=obj_safety,
        ),
        constraint_vector=ConstraintVector(),
    )


def test_evaluate_population_reuses_duplicate_quantized_candidates() -> None:
    evaluator = _CountingEvaluator()
    bridge = OptimizerBridge(
        evaluator=evaluator,  # type: ignore[arg-type]
        fixed_strategy_id="strategy_a",
        search_space_config=SearchSpaceConfig(
            power_min_kw=50.0,
            power_max_kw=500.0,
            duration_min_h=1.0,
            duration_max_h=4.0,
        ),
    )

    results = bridge.evaluate_population(
        ctx=object(),  # type: ignore[arg-type]
        population=[
            np.array([123.0, 2.06]),
            np.array([124.0, 2.08]),
            np.array([176.0, 2.38]),
        ],
    )

    assert len(results) == 3
    assert len(evaluator.calls) == 2
    assert bridge.last_population_evaluation_count == 2
    assert results[0] is results[1]
    assert results[0].decision.rated_power_kw == pytest.approx(100.0)
    assert results[0].decision.duration_h() == pytest.approx(2.0)
    assert results[2].decision.rated_power_kw == pytest.approx(200.0)
    assert results[2].decision.duration_h() == pytest.approx(2.5)


def test_evaluate_population_reuses_supplied_cache_across_calls() -> None:
    evaluator = _CountingEvaluator()
    bridge = OptimizerBridge(
        evaluator=evaluator,  # type: ignore[arg-type]
        fixed_strategy_id="strategy_a",
        search_space_config=SearchSpaceConfig(
            power_min_kw=50.0,
            power_max_kw=500.0,
            duration_min_h=1.0,
            duration_max_h=4.0,
        ),
    )
    evaluation_cache: dict[DecisionCacheKey, FitnessEvaluationResult] = {}

    bridge.evaluate_population(
        ctx=object(),  # type: ignore[arg-type]
        population=[np.array([123.0, 2.06])],
        evaluation_cache=evaluation_cache,
    )
    results = bridge.evaluate_population(
        ctx=object(),  # type: ignore[arg-type]
        population=[
            np.array([124.0, 2.08]),
            np.array([176.0, 2.38]),
        ],
        evaluation_cache=evaluation_cache,
    )

    assert len(results) == 2
    assert len(evaluator.calls) == 2
    assert bridge.last_population_evaluation_count == 1
    assert results[0].decision.rated_power_kw == pytest.approx(100.0)
    assert results[1].decision.rated_power_kw == pytest.approx(200.0)


def test_lemming_optimizer_counts_unique_cached_evaluations_across_generations() -> None:
    evaluator = _CountingEvaluator()
    bridge = OptimizerBridge(
        evaluator=evaluator,  # type: ignore[arg-type]
        fixed_strategy_id="strategy_a",
        search_space_config=SearchSpaceConfig(
            power_min_kw=100.0,
            power_max_kw=100.0,
            duration_min_h=2.0,
            duration_max_h=2.0,
        ),
    )
    optimizer = LemmingOptimizer(
        bridge=bridge,
        config=LemmingOptimizerConfig(
            population_size=3,
            generations=2,
            elite_count=1,
            mutation_rate=0.0,
            reinit_fraction=0.0,
            verbose=False,
        ),
    )

    run_result = optimizer.run(ctx=object())  # type: ignore[arg-type]

    assert len(run_result.population_results) == 3
    assert run_result.all_evaluation_count == 1
    assert len(evaluator.calls) == 1
    assert [record["population_size"] for record in run_result.history] == [3, 3]
    assert [record["evaluator_eval_count"] for record in run_result.history] == [1, 1]


def test_lemming_optimizer_feasible_ranking_uses_user_economic_weights() -> None:
    low_investment = _rankable_result(
        label="low_investment",
        npv_yuan=100_000.0,
        payback_years=6.0,
        investment_yuan=100_000.0,
    )
    high_npv = _rankable_result(
        label="high_npv",
        npv_yuan=900_000.0,
        payback_years=6.0,
        investment_yuan=900_000.0,
    )

    investment_first = LemmingOptimizer(
        bridge=object(),  # type: ignore[arg-type]
        config=LemmingOptimizerConfig(verbose=False),
        safety_economy_tradeoff=0.0,
        economic_metric_weights={"npv": 0.0, "irr": 0.0, "payback": 0.0, "investment": 1.0},
    )
    keys = investment_first._build_ranking_keys([high_npv, low_investment])
    assert keys[id(low_investment)][4] < keys[id(high_npv)][4]

    npv_first = LemmingOptimizer(
        bridge=object(),  # type: ignore[arg-type]
        config=LemmingOptimizerConfig(verbose=False),
        safety_economy_tradeoff=0.0,
        economic_metric_weights={"npv": 1.0, "irr": 0.0, "payback": 0.0, "investment": 0.0},
    )
    keys = npv_first._build_ranking_keys([high_npv, low_investment])
    assert keys[id(high_npv)][4] < keys[id(low_investment)][4]


def test_best_compromise_uses_user_economic_weights() -> None:
    low_investment = _rankable_result(
        label="low_investment",
        npv_yuan=100_000.0,
        payback_years=6.0,
        investment_yuan=100_000.0,
    )
    high_npv = _rankable_result(
        label="high_npv",
        npv_yuan=900_000.0,
        payback_years=6.0,
        investment_yuan=900_000.0,
    )

    assert select_best_compromise(
        [high_npv, low_investment],
        safety_economy_tradeoff=0.0,
        economic_metric_weights={"npv": 0.0, "irr": 0.0, "payback": 0.0, "investment": 1.0},
    ) is low_investment
    assert select_best_compromise(
        [high_npv, low_investment],
        safety_economy_tradeoff=0.0,
        economic_metric_weights={"npv": 1.0, "irr": 0.0, "payback": 0.0, "investment": 0.0},
    ) is high_npv


def test_best_compromise_uses_device_strategy_safety_proxy_when_no_hard_violation() -> None:
    high_economy_high_cycle = _rankable_result(
        label="high_economy_high_cycle",
        npv_yuan=900_000.0,
        payback_years=3.0,
        investment_yuan=900_000.0,
        obj_safety=620.0,
    )
    lower_economy_low_cycle = _rankable_result(
        label="lower_economy_low_cycle",
        npv_yuan=700_000.0,
        payback_years=5.0,
        investment_yuan=1_200_000.0,
        obj_safety=260.0,
    )

    safety_first = {
        "transformer": 0.0,
        "voltage": 0.0,
        "line": 0.0,
        "cycle": 1.0,
    }

    assert select_best_compromise(
        [high_economy_high_cycle, lower_economy_low_cycle],
        safety_economy_tradeoff=1.0,
        safety_metric_weights=safety_first,
    ) is lower_economy_low_cycle

    optimizer = LemmingOptimizer(
        bridge=object(),  # type: ignore[arg-type]
        config=LemmingOptimizerConfig(verbose=False),
        safety_economy_tradeoff=1.0,
        safety_metric_weights=safety_first,
    )
    keys = optimizer._build_ranking_keys([high_economy_high_cycle, lower_economy_low_cycle])
    assert keys[id(lower_economy_low_cycle)][4] < keys[id(high_economy_high_cycle)][4]


def test_weighted_objective_scores_expose_high_is_good_fitness() -> None:
    scores = compute_weighted_objective_scores(
        npv=[100_000.0, 900_000.0],
        irr=[0.08, 0.12],
        payback=[6.0, 4.0],
        investment=[900_000.0, 100_000.0],
        transformer=[2.0, 0.0],
        voltage=[0.02, 0.0],
        line=[10.0, 0.0],
        cycle=[1.0, 0.0],
        safety_economy_tradeoff=0.5,
    )

    assert scores.compromise_cost[1] < scores.compromise_cost[0]
    assert scores.fitness_score[1] > scores.fitness_score[0]
    assert scores.economic_score[1] > scores.economic_score[0]
    assert scores.safety_score[1] > scores.safety_score[0]
