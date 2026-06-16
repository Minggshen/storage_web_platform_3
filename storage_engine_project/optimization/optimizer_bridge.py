from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.optimization.optimization_models import (
    FitnessEvaluationResult,
    StorageDecision,
)
from storage_engine_project.optimization.storage_fitness_evaluator import StorageFitnessEvaluator
from storage_engine_project.simulation.network_constraint_oracle import NetworkConstraintOracle

POWER_QUANTUM_KW: float = 50.0
DURATION_QUANTUM_H: float = 0.25
DecisionCacheKey = tuple[str, float, float]


@dataclass(slots=True)
class SearchSpaceConfig:
    power_min_kw: float
    power_max_kw: float
    duration_min_h: float
    duration_max_h: float

    def __post_init__(self) -> None:
        if self.power_min_kw <= 0 or self.power_max_kw <= 0:
            raise ValueError("功率上下界必须大于 0。")
        if self.power_min_kw > self.power_max_kw:
            raise ValueError("power_min_kw 不能大于 power_max_kw。")
        if self.duration_min_h <= 0 or self.duration_max_h <= 0:
            raise ValueError("时长上下界必须大于 0。")
        if self.duration_min_h > self.duration_max_h:
            raise ValueError("duration_min_h 不能大于 duration_max_h。")


class OptimizerBridge:
    def __init__(
        self,
        evaluator: StorageFitnessEvaluator,
        fixed_strategy_id: str,
        search_space_config: SearchSpaceConfig,
    ) -> None:
        if not str(fixed_strategy_id).strip():
            raise ValueError("fixed_strategy_id 不能为空。")
        self.evaluator = evaluator
        self.fixed_strategy_id = str(fixed_strategy_id)
        self.search_space_config = search_space_config
        self.last_population_evaluation_count = 0

    def vector_to_decision(self, x: np.ndarray | list[float]) -> StorageDecision:
        arr = np.asarray(x, dtype=float).reshape(-1)
        if arr.shape[0] < 2:
            raise ValueError("候选向量长度至少应为 2：[power_kw, duration_h]")

        power_kw = float(arr[0])
        duration_h = float(arr[1])
        energy_kwh = power_kw * duration_h

        return StorageDecision(
            strategy_id=self.fixed_strategy_id,
            rated_power_kw=power_kw,
            rated_energy_kwh=energy_kwh,
        )

    def decision_to_vector(self, decision: StorageDecision) -> np.ndarray:
        if decision.strategy_id != self.fixed_strategy_id:
            raise KeyError(f"未知策略：{decision.strategy_id}")
        return np.array(
            [
                float(decision.rated_power_kw),
                float(decision.duration_h()),
            ],
            dtype=float,
        )

    def get_global_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        ss = self.search_space_config
        lb = np.array([float(ss.power_min_kw), float(ss.duration_min_h)], dtype=float)
        ub = np.array(
            [float(ss.power_max_kw), float(ss.duration_max_h)],
            dtype=float,
        )
        return lb, ub

    def clip_vector_to_bounds(self, x: np.ndarray | list[float]) -> np.ndarray:
        x = np.asarray(x, dtype=float).reshape(-1)
        lb, ub = self.get_global_bounds()
        if x.shape[0] < 2:
            raise ValueError("向量长度至少为 2。")

        x_clip = x.copy()
        x_clip[:2] = np.clip(x_clip[:2], lb, ub)
        ss = self.search_space_config

        # 量化功率和时长以提升缓存命中率与结果稳定性
        if POWER_QUANTUM_KW > 0:
            x_clip[0] = round(float(x_clip[0]) / POWER_QUANTUM_KW) * POWER_QUANTUM_KW
        if DURATION_QUANTUM_H > 0:
            x_clip[1] = round(float(x_clip[1]) / DURATION_QUANTUM_H) * DURATION_QUANTUM_H

        # 量化后重新裁剪到策略边界
        x_clip[0] = np.clip(x_clip[0], ss.power_min_kw, ss.power_max_kw)
        x_clip[1] = np.clip(x_clip[1], ss.duration_min_h, ss.duration_max_h)
        return x_clip

    @staticmethod
    def _decision_cache_key(decision: StorageDecision) -> DecisionCacheKey:
        return (
            decision.strategy_id,
            round(float(decision.rated_power_kw), 9),
            round(float(decision.duration_h()), 9),
        )

    def evaluate_vector(
        self,
        ctx: AnnualOperationContext,
        x: np.ndarray | list[float],
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: NetworkConstraintOracle | None = None,
    ) -> FitnessEvaluationResult:
        x_clip = self.clip_vector_to_bounds(x)
        decision = self.vector_to_decision(x_clip)
        return self.evaluator.evaluate_decision(
            ctx=ctx,
            decision=decision,
            actual_load_matrix_kw=actual_load_matrix_kw,
            actual_pv_matrix_kw=actual_pv_matrix_kw,
            network_oracle=network_oracle,
        )

    def evaluate_population(
        self,
        ctx: AnnualOperationContext,
        population: Iterable[np.ndarray | list[float]],
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: NetworkConstraintOracle | None = None,
        evaluation_cache: dict[DecisionCacheKey, FitnessEvaluationResult] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[FitnessEvaluationResult]:
        results: list[FitnessEvaluationResult] = []
        evaluated: dict[DecisionCacheKey, FitnessEvaluationResult] = (
            evaluation_cache if evaluation_cache is not None else {}
        )
        unique_evaluation_count = 0
        population_items = list(population)
        population_size = len(population_items)
        for idx, x in enumerate(population_items, start=1):
            x_clip = self.clip_vector_to_bounds(x)
            decision = self.vector_to_decision(x_clip)
            key = self._decision_cache_key(decision)

            res = evaluated.get(key)
            if res is None:
                if progress_callback is not None:
                    progress_callback({
                        "event": "ga_candidate_start",
                        "candidate_index": idx,
                        "population_size": population_size,
                        "unique_candidate_index": unique_evaluation_count + 1,
                        "strategy_id": decision.strategy_id,
                        "rated_power_kw": float(decision.rated_power_kw),
                        "duration_h": float(decision.duration_h()),
                    })
                res = self.evaluator.evaluate_decision(
                    ctx=ctx,
                    decision=decision,
                    actual_load_matrix_kw=actual_load_matrix_kw,
                    actual_pv_matrix_kw=actual_pv_matrix_kw,
                    network_oracle=network_oracle,
                )
                evaluated[key] = res
                unique_evaluation_count += 1
                if progress_callback is not None:
                    progress_callback({
                        "event": "ga_candidate_complete",
                        "candidate_index": idx,
                        "population_size": population_size,
                        "unique_candidate_index": unique_evaluation_count,
                        "strategy_id": decision.strategy_id,
                        "rated_power_kw": float(decision.rated_power_kw),
                        "duration_h": float(decision.duration_h()),
                    })
            elif progress_callback is not None:
                progress_callback({
                    "event": "ga_candidate_cache_hit",
                    "candidate_index": idx,
                    "population_size": population_size,
                    "unique_candidate_index": unique_evaluation_count,
                    "strategy_id": decision.strategy_id,
                    "rated_power_kw": float(decision.rated_power_kw),
                    "duration_h": float(decision.duration_h()),
                })
            results.append(res)
        self.last_population_evaluation_count = unique_evaluation_count
        return results

    @staticmethod
    def result_to_summary_row(
        result: FitnessEvaluationResult,
    ) -> dict[str, Any]:
        return result.summary_dict()

    @staticmethod
    def results_to_dataframe(
        results: list[FitnessEvaluationResult],
    ) -> pd.DataFrame:
        rows = [r.summary_dict() for r in results]
        return pd.DataFrame(rows)

    @staticmethod
    def result_to_objective_tuple(
        result: FitnessEvaluationResult,
    ) -> tuple[float, float, float, float]:
        return result.objective_vector.as_tuple()

    @staticmethod
    def result_to_constraint_dict(
        result: FitnessEvaluationResult,
    ) -> dict[str, float]:
        return result.constraint_vector.as_dict()

    @staticmethod
    def build_archive_records(
        results: list[FitnessEvaluationResult],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for r in results:
            row = r.summary_dict()
            row["objective_tuple"] = r.objective_vector.as_tuple()
            row["constraint_total_violation"] = r.constraint_vector.total_violation()
            row["constraint_max_violation"] = r.constraint_vector.max_violation()
            records.append(row)
        return records
