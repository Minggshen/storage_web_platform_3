from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.optimization.optimization_models import (
    FitnessEvaluationResult,
    StorageDecision,
)
from storage_engine_project.optimization.storage_fitness_evaluator import StorageFitnessEvaluator
from storage_engine_project.simulation.network_constraint_oracle import NetworkConstraintOracle


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
        strategy_ids: list[str],
        search_spaces: dict[str, SearchSpaceConfig],
    ) -> None:
        if not strategy_ids:
            raise ValueError("strategy_ids 不能为空。")
        self.evaluator = evaluator
        self.strategy_ids = list(strategy_ids)
        self.search_spaces = dict(search_spaces)

        for sid in self.strategy_ids:
            if sid not in self.search_spaces:
                raise KeyError(f"策略 {sid} 未提供 SearchSpaceConfig。")

    def vector_to_decision(self, x: np.ndarray | list[float]) -> StorageDecision:
        arr = np.asarray(x, dtype=float).reshape(-1)
        if arr.shape[0] < 3:
            raise ValueError("候选向量长度至少应为 3：[strategy_selector, power_kw, duration_h]")

        strategy_index = int(np.clip(round(arr[0]), 0, len(self.strategy_ids) - 1))
        strategy_id = self.strategy_ids[strategy_index]

        power_kw = float(arr[1])
        duration_h = float(arr[2])
        energy_kwh = power_kw * duration_h

        return StorageDecision(
            strategy_id=strategy_id,
            rated_power_kw=power_kw,
            rated_energy_kwh=energy_kwh,
        )

    def decision_to_vector(self, decision: StorageDecision) -> np.ndarray:
        if decision.strategy_id not in self.strategy_ids:
            raise KeyError(f"未知策略：{decision.strategy_id}")
        strategy_index = float(self.strategy_ids.index(decision.strategy_id))
        return np.array(
            [
                strategy_index,
                float(decision.rated_power_kw),
                float(decision.duration_h()),
            ],
            dtype=float,
        )

    def get_global_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        power_lows = [self.search_spaces[sid].power_min_kw for sid in self.strategy_ids]
        power_highs = [self.search_spaces[sid].power_max_kw for sid in self.strategy_ids]
        dur_lows = [self.search_spaces[sid].duration_min_h for sid in self.strategy_ids]
        dur_highs = [self.search_spaces[sid].duration_max_h for sid in self.strategy_ids]

        lb = np.array([0.0, float(min(power_lows)), float(min(dur_lows))], dtype=float)
        ub = np.array(
            [float(len(self.strategy_ids) - 1), float(max(power_highs)), float(max(dur_highs))],
            dtype=float,
        )
        return lb, ub

    def clip_vector_to_bounds(self, x: np.ndarray | list[float]) -> np.ndarray:
        x = np.asarray(x, dtype=float).reshape(-1)
        lb, ub = self.get_global_bounds()
        if x.shape[0] < 3:
            raise ValueError("向量长度至少为 3。")

        x_clip = x.copy()
        x_clip[:3] = np.clip(x_clip[:3], lb, ub)

        decision = self.vector_to_decision(x_clip)
        ss = self.search_spaces[decision.strategy_id]
        x_clip[1] = np.clip(x_clip[1], ss.power_min_kw, ss.power_max_kw)
        x_clip[2] = np.clip(x_clip[2], ss.duration_min_h, ss.duration_max_h)
        return x_clip

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
    ) -> list[FitnessEvaluationResult]:
        results: list[FitnessEvaluationResult] = []
        for x in population:
            res = self.evaluate_vector(
                ctx=ctx,
                x=x,
                actual_load_matrix_kw=actual_load_matrix_kw,
                actual_pv_matrix_kw=actual_pv_matrix_kw,
                network_oracle=network_oracle,
            )
            results.append(res)
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