from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from storage_engine_project.optimization.optimization_models import (  # noqa: E402
    ConstraintVector,
    FitnessEvaluationResult,
    ObjectiveVector,
    ScreeningResult,
    StorageDecision,
)
from storage_engine_project.optimization.optimizer_bridge import (  # noqa: E402
    DecisionCacheKey,
    OptimizerBridge,
    SearchSpaceConfig,
)
from storage_engine_project.optimization.pareto_utils import update_archive  # noqa: E402


class SlowCountingEvaluator:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = float(delay_s)
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
        if self.delay_s > 0:
            time.sleep(self.delay_s)
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


def _population_batches() -> list[list[np.ndarray]]:
    return [
        [
            np.array([0.0, 123.0, 2.06]),
            np.array([0.0, 124.0, 2.08]),
            np.array([0.0, 176.0, 2.38]),
            np.array([0.0, 198.0, 2.51]),
            np.array([0.0, 251.0, 3.01]),
        ],
        [
            np.array([0.0, 124.0, 2.08]),
            np.array([0.0, 252.0, 2.99]),
            np.array([0.0, 301.0, 3.24]),
            np.array([0.0, 299.0, 3.26]),
            np.array([0.0, 50.0, 1.00]),
        ],
    ]


def run_benchmark(delay_ms: float) -> dict[str, Any]:
    evaluator = SlowCountingEvaluator(delay_s=max(0.0, delay_ms) / 1000.0)
    bridge = OptimizerBridge(
        evaluator=evaluator,  # type: ignore[arg-type]
        strategy_ids=["strategy_a"],
        search_spaces={
            "strategy_a": SearchSpaceConfig(
                power_min_kw=50.0,
                power_max_kw=500.0,
                duration_min_h=1.0,
                duration_max_h=4.0,
            )
        },
    )

    cache: dict[DecisionCacheKey, FitnessEvaluationResult] = {}
    archive: list[FitnessEvaluationResult] = []
    generation_result_lengths: list[int] = []
    unique_evaluations_by_generation: list[int] = []

    started = time.perf_counter()
    for population in _population_batches():
        results = bridge.evaluate_population(
            ctx=object(),  # type: ignore[arg-type]
            population=population,
            evaluation_cache=cache,
        )
        if len(results) != len(population):
            raise AssertionError("result list length must stay equal to population length")
        generation_result_lengths.append(len(results))
        unique_evaluations_by_generation.append(bridge.last_population_evaluation_count)
        archive = update_archive(archive, results)
    elapsed_s = time.perf_counter() - started

    total_slots = sum(generation_result_lengths)
    actual_calls = len(evaluator.calls)
    if total_slots != 10 or actual_calls != 5 or unique_evaluations_by_generation != [3, 2]:
        raise AssertionError("benchmark fixture no longer exercises the expected cache reuse shape")

    return {
        "population_slots": total_slots,
        "generation_result_lengths": generation_result_lengths,
        "expected_without_cache_calls": total_slots,
        "actual_evaluator_calls": actual_calls,
        "unique_evaluations_by_generation": unique_evaluations_by_generation,
        "cache_entries": len(cache),
        "reused_candidate_slots": total_slots - actual_calls,
        "result_lengths_preserved": True,
        "archive_size_after_updates": len(archive),
        "wall_time_s": round(elapsed_s, 6),
        "estimated_uncached_sleep_s": round(total_slots * max(0.0, delay_ms) / 1000.0, 6),
        "observed_sleep_s": round(actual_calls * max(0.0, delay_ms) / 1000.0, 6),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark OptimizerBridge duplicate-candidate cache.")
    parser.add_argument("--delay-ms", type=float, default=10.0, help="Fake evaluator delay per real evaluation.")
    args = parser.parse_args(argv)

    print(json.dumps(run_benchmark(delay_ms=float(args.delay_ms)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
