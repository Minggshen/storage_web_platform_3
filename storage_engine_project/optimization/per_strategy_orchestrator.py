from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.optimization.lemming_optimizer import (
    LemmingOptimizationRunResult,
    LemmingOptimizer,
    LemmingOptimizerConfig,
)
from storage_engine_project.optimization.objective_scoring import DEFAULT_DEVICE_SAFETY_BETA
from storage_engine_project.optimization.optimization_models import FitnessEvaluationResult
from storage_engine_project.optimization.optimizer_bridge import OptimizerBridge, SearchSpaceConfig
from storage_engine_project.optimization.pareto_utils import select_best_compromise


@dataclass(slots=True)
class PerStrategyOrchestratorConfig:
    optimizer_config: LemmingOptimizerConfig | None = None
    generations_per_strategy: int = 3
    safety_economy_tradeoff: float = 0.5
    economic_metric_weights: dict[str, float] | None = None
    safety_metric_weights: dict[str, float] | None = None
    device_safety_beta: float = DEFAULT_DEVICE_SAFETY_BETA


def run_per_strategy_ga(
    evaluator: Any,
    ctx: AnnualOperationContext,
    strategy_ids: list[str],
    search_spaces: dict[str, SearchSpaceConfig],
    config: PerStrategyOrchestratorConfig,
    network_oracle: Any = None,
    actual_load_matrix_kw: np.ndarray | None = None,
    actual_pv_matrix_kw: np.ndarray | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> LemmingOptimizationRunResult:
    """Run one 2D GA per strategy, then compare all retained candidates globally."""
    del network_oracle

    strategy_list = [str(strategy_id) for strategy_id in strategy_ids if str(strategy_id).strip()]
    if not strategy_list:
        raise ValueError("strategy_ids 不能为空。")

    base_config = config.optimizer_config or LemmingOptimizerConfig()
    generations_per_strategy = max(1, int(config.generations_per_strategy or base_config.generations or 1))
    strategy_total = len(strategy_list)
    global_generations = strategy_total * generations_per_strategy

    original_full_recheck_flag = _get_full_recheck_flag(evaluator)
    _set_full_recheck_flag(evaluator, False)
    try:
        per_strategy_results: list[tuple[int, str, LemmingOptimizationRunResult]] = []
        for strategy_index, strategy_id in enumerate(strategy_list):
            if strategy_id not in search_spaces:
                raise KeyError(f"策略 {strategy_id} 未提供 SearchSpaceConfig。")

            optimizer_config = replace(
                base_config,
                generations=generations_per_strategy,
                random_seed=int(base_config.random_seed) + strategy_index,
            )
            bridge = OptimizerBridge(
                evaluator=evaluator,
                fixed_strategy_id=strategy_id,
                search_space_config=search_spaces[strategy_id],
            )
            optimizer = LemmingOptimizer(
                bridge=bridge,
                config=optimizer_config,
                safety_economy_tradeoff=config.safety_economy_tradeoff,
                economic_metric_weights=config.economic_metric_weights,
                safety_metric_weights=config.safety_metric_weights,
                device_safety_beta=config.device_safety_beta,
            )

            if progress_callback is not None:
                progress_callback({
                    "event": "per_strategy_ga_start",
                    "strategy_id": strategy_id,
                    "strategy_index": strategy_index,
                    "strategy_ordinal": strategy_index + 1,
                    "strategy_total": strategy_total,
                    "generation": strategy_index * generations_per_strategy + 1,
                    "generations": global_generations,
                    "local_generations": generations_per_strategy,
                })

            run_result = optimizer.run(
                ctx=ctx,
                actual_load_matrix_kw=actual_load_matrix_kw,
                actual_pv_matrix_kw=actual_pv_matrix_kw,
                network_oracle=None,
                progress_callback=_global_progress_wrapper(
                    progress_callback=progress_callback,
                    strategy_id=strategy_id,
                    strategy_index=strategy_index,
                    strategy_total=strategy_total,
                    generations_per_strategy=generations_per_strategy,
                    global_generations=global_generations,
                ),
            )
            per_strategy_results.append((strategy_index, strategy_id, run_result))

            if progress_callback is not None:
                progress_callback({
                    "event": "per_strategy_ga_complete",
                    "strategy_id": strategy_id,
                    "strategy_index": strategy_index,
                    "strategy_ordinal": strategy_index + 1,
                    "strategy_total": strategy_total,
                    "generation": (strategy_index + 1) * generations_per_strategy,
                    "generations": global_generations,
                    "local_generations": generations_per_strategy,
                    "archive_size": len(run_result.archive_results),
                    "evaluator_eval_count": run_result.all_evaluation_count,
                })
    finally:
        _set_full_recheck_flag(evaluator, original_full_recheck_flag)

    return _merge_run_results(per_strategy_results, config=config)


def _global_progress_wrapper(
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    strategy_id: str,
    strategy_index: int,
    strategy_total: int,
    generations_per_strategy: int,
    global_generations: int,
) -> Callable[[dict[str, Any]], None] | None:
    if progress_callback is None:
        return None

    def _emit(event: dict[str, Any]) -> None:
        local_generation = _safe_int(event.get("generation"), 1)
        local_generation = max(1, min(generations_per_strategy, local_generation))
        global_generation = strategy_index * generations_per_strategy + local_generation
        progress_callback({
            **event,
            "generation": global_generation,
            "generations": global_generations,
            "global_generation": global_generation,
            "local_generation": local_generation,
            "local_generations": generations_per_strategy,
            "strategy_id": strategy_id,
            "strategy_index": strategy_index,
            "strategy_ordinal": strategy_index + 1,
            "strategy_total": strategy_total,
        })

    return _emit


def _merge_run_results(
    per_strategy_results: Iterable[tuple[int, str, LemmingOptimizationRunResult]],
    *,
    config: PerStrategyOrchestratorConfig,
) -> LemmingOptimizationRunResult:
    archive_results: list[FitnessEvaluationResult] = []
    population_results: list[FitnessEvaluationResult] = []
    history: list[dict[str, Any]] = []
    all_evaluation_count = 0

    materialized = list(per_strategy_results)
    generations_per_strategy = max(1, int(config.generations_per_strategy or 1))
    strategy_total = len(materialized)

    for strategy_index, strategy_id, run_result in materialized:
        archive_results = _append_unique_results(archive_results, run_result.archive_results)
        population_results = _append_unique_results(population_results, run_result.population_results)
        all_evaluation_count += int(run_result.all_evaluation_count or 0)

        for record in run_result.history:
            local_generation = _safe_int(record.get("generation"), 1)
            global_generation = strategy_index * generations_per_strategy + local_generation
            merged_record = dict(record)
            merged_record["generation"] = global_generation
            merged_record["global_generation"] = global_generation
            merged_record["local_generation"] = local_generation
            merged_record["local_generations"] = generations_per_strategy
            merged_record["strategy_id"] = strategy_id
            merged_record["strategy_index"] = strategy_index
            merged_record["strategy_ordinal"] = strategy_index + 1
            merged_record["strategy_total"] = strategy_total
            history.append(merged_record)

    best_result = select_best_compromise(
        archive_results,
        safety_economy_tradeoff=config.safety_economy_tradeoff,
        economic_metric_weights=config.economic_metric_weights,
        safety_metric_weights=config.safety_metric_weights,
        device_safety_beta=config.device_safety_beta,
    )

    return LemmingOptimizationRunResult(
        archive_results=archive_results,
        population_results=population_results,
        history=history,
        best_result=best_result,
        all_evaluation_count=all_evaluation_count,
    )


def _append_unique_results(
    current: list[FitnessEvaluationResult],
    candidates: Iterable[FitnessEvaluationResult],
) -> list[FitnessEvaluationResult]:
    out = list(current)
    seen = {_solution_key(result) for result in out}
    for candidate in candidates:
        key = _solution_key(candidate)
        if key in seen:
            continue
        out.append(candidate)
        seen.add(key)
    return out


def _solution_key(result: FitnessEvaluationResult) -> tuple[str, float, float]:
    decision = result.decision
    return (
        str(decision.strategy_id),
        round(float(decision.rated_power_kw), 9),
        round(float(decision.rated_energy_kwh), 9),
    )


def _get_full_recheck_flag(evaluator: Any) -> bool | None:
    config = getattr(evaluator, "config", None)
    if config is None or not hasattr(config, "full_recheck_for_fast_feasible_only"):
        return None
    return bool(getattr(config, "full_recheck_for_fast_feasible_only"))


def _set_full_recheck_flag(evaluator: Any, value: bool | None) -> None:
    if value is None:
        return
    config = getattr(evaluator, "config", None)
    if config is not None and hasattr(config, "full_recheck_for_fast_feasible_only"):
        setattr(config, "full_recheck_for_fast_feasible_only", bool(value))


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except Exception:
        return int(default)
