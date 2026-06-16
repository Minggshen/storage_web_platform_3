from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.logging_config import get_logger
from storage_engine_project.optimization.optimizer_bridge import (
    DecisionCacheKey,
    OptimizerBridge,
)
from storage_engine_project.optimization.objective_scoring import (
    DEFAULT_DEVICE_SAFETY_BETA,
    compute_weighted_objective_scores,
    device_safety_cost_metric,
    device_strategy_safety_metric,
)
from storage_engine_project.optimization.optimization_models import FitnessEvaluationResult
from storage_engine_project.optimization.pareto_utils import select_best_compromise, update_archive
from storage_engine_project.simulation.network_constraint_oracle import NetworkConstraintOracle

logger = get_logger(__name__)


def _finite_float(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


@dataclass(slots=True)
class LemmingOptimizerConfig:
    population_size: int = 16
    generations: int = 8
    elite_count: int = 4
    mutation_rate: float = 0.35
    mutation_scale_power: float = 0.15
    mutation_scale_duration: float = 0.15
    random_seed: int = 42

    reinit_fraction: float = 0.20
    tournament_size: int = 3

    # 改进#4: 自适应种群规模
    enable_adaptive_population: bool = False
    min_population_size: int = 12
    max_population_size: int = 24
    adaptive_growth_threshold: float = 0.15
    adaptive_shrink_threshold: float = 0.05
    adaptive_signal_growth_threshold: float = 0.30
    adaptive_signal_shrink_threshold: float = -0.30
    adaptive_target_improve: float = 0.05
    adaptive_target_diversity: float = 0.25
    adaptive_target_recheck_rate: float = 0.30
    adaptive_scale_improve: float = 0.05
    adaptive_scale_diversity: float = 0.15
    adaptive_scale_recheck_rate: float = 0.20
    adaptive_weight_stagnation: float = 0.40
    adaptive_weight_diversity: float = 0.35
    adaptive_weight_recheck_rate: float = 0.25
    adaptive_recheck_rate_block_growth: float = 0.50
    adaptive_recheck_rate_force_shrink: float = 0.70

    verbose: bool = True


@dataclass(slots=True)
class LemmingOptimizationRunResult:
    archive_results: list[FitnessEvaluationResult]
    population_results: list[FitnessEvaluationResult]
    history: list[dict[str, Any]]
    best_result: FitnessEvaluationResult | None
    all_evaluation_count: int


class LemmingOptimizer:
    def __init__(
        self,
        bridge: OptimizerBridge,
        config: LemmingOptimizerConfig | None = None,
        safety_economy_tradeoff: float = 0.5,
        economic_metric_weights: dict[str, float] | None = None,
        safety_metric_weights: dict[str, float] | None = None,
        device_safety_beta: float = DEFAULT_DEVICE_SAFETY_BETA,
    ) -> None:
        self.bridge = bridge
        self.config = config or LemmingOptimizerConfig()
        self.safety_economy_tradeoff = float(safety_economy_tradeoff)
        self.economic_metric_weights = dict(economic_metric_weights or {})
        self.safety_metric_weights = dict(safety_metric_weights or {})
        self.device_safety_beta = float(device_safety_beta)
        self.rng = np.random.default_rng(self.config.random_seed)

    def run(
        self,
        ctx: AnnualOperationContext,
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: NetworkConstraintOracle | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> LemmingOptimizationRunResult:
        cfg = self.config

        population = self._initialize_population()
        archive: list[FitnessEvaluationResult] = []
        history: list[dict[str, Any]] = []
        all_eval_count = 0
        run_evaluation_cache: dict[DecisionCacheKey, FitnessEvaluationResult] = {}

        for gen in range(cfg.generations):
            _gen_t0 = time.perf_counter()
            fast_before = self._evaluator_counter("_fast_proxy_count")
            recheck_before = self._evaluator_counter("_full_recheck_count")
            if progress_callback is not None:
                progress_callback({
                    "event": "ga_generation_start",
                    "generation": gen + 1,
                    "generations": cfg.generations,
                    "population_size": len(population),
                    "evaluator_eval_count": all_eval_count,
                })

            def _population_progress(event: dict[str, Any]) -> None:
                if progress_callback is None:
                    return
                progress_callback({
                    **event,
                    "generation": gen + 1,
                    "generations": cfg.generations,
                })

            results = self.bridge.evaluate_population(
                ctx=ctx,
                population=population,
                actual_load_matrix_kw=actual_load_matrix_kw,
                actual_pv_matrix_kw=actual_pv_matrix_kw,
                network_oracle=network_oracle,
                evaluation_cache=run_evaluation_cache,
                progress_callback=_population_progress if progress_callback is not None else None,
            )
            all_eval_count += self.bridge.last_population_evaluation_count
            _gen_elapsed = time.perf_counter() - _gen_t0
            fast_delta = max(0, self._evaluator_counter("_fast_proxy_count") - fast_before)
            recheck_delta = max(0, self._evaluator_counter("_full_recheck_count") - recheck_before)

            archive = update_archive(archive, results)
            best_compromise = select_best_compromise(
                archive,
                safety_economy_tradeoff=self.safety_economy_tradeoff,
                economic_metric_weights=self.economic_metric_weights,
                safety_metric_weights=self.safety_metric_weights,
                device_safety_beta=self.device_safety_beta,
            )

            gen_record = self._build_generation_record(
                generation=gen + 1,
                results=results,
                archive=archive,
                best_compromise=best_compromise,
                generation_wall_time_s=_gen_elapsed,
                evaluator_eval_count=all_eval_count,
                population_vectors=population,
                fast_eval_count=fast_delta,
                recheck_eval_count=recheck_delta,
                previous_best_compromise_cost=history[-1].get("best_compromise_cost") if history else None,
            )
            history.append(gen_record)

            if cfg.verbose:
                self._print_generation_record(gen_record)

            if progress_callback is not None:
                progress_callback({
                    "event": "ga_generation_complete",
                    "generation": gen + 1,
                    "generations": cfg.generations,
                    "population_size": len(results),
                    "unique_evaluation_count": self.bridge.last_population_evaluation_count,
                    "evaluator_eval_count": all_eval_count,
                    "generation_wall_time_s": _gen_elapsed,
                })

            target_pop_size = self._adaptive_population_size(gen, history) if cfg.enable_adaptive_population else cfg.population_size
            population = self._next_population(results, target_size=target_pop_size)

        final_best = select_best_compromise(
            archive,
            safety_economy_tradeoff=self.safety_economy_tradeoff,
            economic_metric_weights=self.economic_metric_weights,
            safety_metric_weights=self.safety_metric_weights,
            device_safety_beta=self.device_safety_beta,
        )

        return LemmingOptimizationRunResult(
            archive_results=archive,
            population_results=results,
            history=history,
            best_result=final_best,
            all_evaluation_count=all_eval_count,
        )

    def _initialize_population(self) -> list[np.ndarray]:
        lb, ub = self.bridge.get_global_bounds()
        population: list[np.ndarray] = []

        for _ in range(self.config.population_size):
            x = np.array(
                [
                    self.rng.uniform(lb[0], ub[0]),
                    self.rng.uniform(lb[1], ub[1]),
                ],
                dtype=float,
            )
            x = self.bridge.clip_vector_to_bounds(x)
            population.append(x)

        return population

    def _next_population(
        self,
        results: list[FitnessEvaluationResult],
        target_size: int | None = None,
    ) -> list[np.ndarray]:
        cfg = self.config
        if target_size is None:
            target_size = cfg.population_size

        ranking_keys = self._build_ranking_keys(results)
        ranked = sorted(results, key=lambda result: ranking_keys[id(result)])
        elites = ranked[: max(1, cfg.elite_count)]

        next_pop: list[np.ndarray] = []
        for elite in elites:
            next_pop.append(self.bridge.decision_to_vector(elite.decision))

        while len(next_pop) < target_size:
            if self.rng.random() < cfg.reinit_fraction:
                next_pop.append(self._random_candidate())
                continue

            p1 = self._tournament_select(ranked, ranking_keys)
            p2 = self._tournament_select(ranked, ranking_keys)

            x1 = self.bridge.decision_to_vector(p1.decision)
            x2 = self.bridge.decision_to_vector(p2.decision)

            child = self._crossover(x1, x2)
            child = self._mutate(child)
            child = self.bridge.clip_vector_to_bounds(child)

            next_pop.append(child)

        return next_pop[:target_size]

    def _build_ranking_keys(
        self,
        results: list[FitnessEvaluationResult],
    ) -> dict[int, tuple[float, float, float, float, float, float]]:
        """分层约束排序：约束优先，严格可行解内用用户设置的经济/安全加权目标。"""
        feasible = [result for result in results if result.feasible]
        compromise_costs: dict[int, float] = {}
        if feasible:
            compromise_costs = self._weighted_compromise_costs(feasible)

        keys: dict[int, tuple[float, float, float, float, float, float]] = {}
        for result in results:
            cv = result.constraint_vector
            feasible_penalty = 0.0 if result.feasible else 1.0
            obj = result.objective_vector.as_tuple()
            keys[id(result)] = (
                feasible_penalty,
                cv.hard_constraint_violation(),
                cv.medium_constraint_violation(),
                cv.soft_constraint_violation(),
                compromise_costs.get(id(result), float(sum(obj))),
                obj[0],
            )
        return keys

    def _weighted_compromise_costs(
        self,
        feasible: list[FitnessEvaluationResult],
    ) -> dict[int, float]:
        scores = compute_weighted_objective_scores(
            npv=[self._npv_metric(result) for result in feasible],
            irr=[self._irr_metric(result) for result in feasible],
            payback=[self._payback_metric(result) for result in feasible],
            investment=[self._investment_metric(result) for result in feasible],
            transformer=[result.constraint_vector.transformer_violation_hours for result in feasible],
            voltage=[result.constraint_vector.voltage_violation_pu for result in feasible],
            line=[result.constraint_vector.line_loading_violation_pct for result in feasible],
            cycle=[device_strategy_safety_metric(result) for result in feasible],
            safety_economy_tradeoff=self.safety_economy_tradeoff,
            economic_metric_weights=self.economic_metric_weights,
            safety_metric_weights=self.safety_metric_weights,
            device_safety_cost=self._device_safety_costs(feasible),
            device_safety_beta=self.device_safety_beta,
        )
        return {
            id(result): float(scores.compromise_cost[index])
            for index, result in enumerate(feasible)
        }

    @staticmethod
    def _device_safety_costs(
        feasible: list[FitnessEvaluationResult],
    ) -> list[float] | None:
        costs = [device_safety_cost_metric(result) for result in feasible]
        if not any(cost is not None for cost in costs):
            return None
        return [float(cost) if cost is not None else float("nan") for cost in costs]

    @staticmethod
    def _investment_metric(result: FitnessEvaluationResult) -> float:
        financial = result.lifecycle_financial_result
        if financial is not None:
            return float(financial.initial_investment_yuan)
        return float(result.objective_vector.obj_investment)

    @staticmethod
    def _npv_metric(result: FitnessEvaluationResult) -> float:
        financial = result.lifecycle_financial_result
        if financial is not None:
            return float(financial.npv_yuan)
        return -float(result.objective_vector.obj_npv)

    @staticmethod
    def _irr_metric(result: FitnessEvaluationResult) -> float:
        financial = result.lifecycle_financial_result
        if financial is not None and financial.irr is not None:
            return float(financial.irr)
        return 0.0

    @staticmethod
    def _payback_metric(result: FitnessEvaluationResult) -> float:
        financial = result.lifecycle_financial_result
        if financial is not None and financial.simple_payback_years is not None:
            return float(financial.simple_payback_years)
        return float(result.objective_vector.obj_payback)

    def _tournament_select(
        self,
        ranked_results: list[FitnessEvaluationResult],
        ranking_keys: dict[int, tuple[float, float, float, float, float, float]],
    ) -> FitnessEvaluationResult:
        idxs = self.rng.choice(
            len(ranked_results),
            size=min(self.config.tournament_size, len(ranked_results)),
            replace=False,
        )
        subset = [ranked_results[i] for i in idxs]
        return min(subset, key=lambda result: ranking_keys[id(result)])

    def _crossover(self, x1: np.ndarray, x2: np.ndarray) -> np.ndarray:
        alpha = self.rng.uniform(0.0, 1.0)
        return alpha * x1 + (1.0 - alpha) * x2

    def _mutate(self, x: np.ndarray) -> np.ndarray:
        cfg = self.config
        out = x.copy()

        if self.rng.random() < cfg.mutation_rate:
            out[0] *= 1.0 + self.rng.normal(0.0, cfg.mutation_scale_power)

        if self.rng.random() < cfg.mutation_rate:
            out[1] *= 1.0 + self.rng.normal(0.0, cfg.mutation_scale_duration)

        return out

    def _adaptive_population_size(self, generation: int, history: list[dict]) -> int:
        """根据停滞、分散度和精评触发率调整种群规模。"""
        cfg = self.config
        if generation < 1 or len(history) < 1:
            return cfg.population_size

        latest = history[-1]
        current_size = int(latest.get("population_size", cfg.population_size) or cfg.population_size)
        signal = float(latest.get("adaptive_signal", 0.0) or 0.0)
        recheck_rate = float(latest.get("fine_eval_trigger_rate", 0.0) or 0.0)

        if recheck_rate > cfg.adaptive_recheck_rate_force_shrink:
            return int(max(current_size - 4, cfg.min_population_size))
        if signal > cfg.adaptive_signal_growth_threshold:
            if recheck_rate > cfg.adaptive_recheck_rate_block_growth:
                return current_size
            return int(min(current_size + 2, cfg.max_population_size))
        if signal < cfg.adaptive_signal_shrink_threshold:
            return int(max(current_size - 2, cfg.min_population_size))
        return int(min(max(current_size, cfg.min_population_size), cfg.max_population_size))

    def _random_candidate(self) -> np.ndarray:
        lb, ub = self.bridge.get_global_bounds()
        x = np.array(
            [
                self.rng.uniform(lb[0], ub[0]),
                self.rng.uniform(lb[1], ub[1]),
            ],
            dtype=float,
        )
        return self.bridge.clip_vector_to_bounds(x)

    def _build_generation_record(
        self,
        generation: int,
        results: list[FitnessEvaluationResult],
        archive: list[FitnessEvaluationResult],
        best_compromise: FitnessEvaluationResult | None,
        generation_wall_time_s: float = 0.0,
        evaluator_eval_count: int = 0,
        population_vectors: list[np.ndarray] | None = None,
        fast_eval_count: int = 0,
        recheck_eval_count: int = 0,
        previous_best_compromise_cost: float | None = None,
    ) -> dict[str, Any]:
        feasible = [r for r in results if r.feasible]

        record: dict[str, Any] = {
            "generation": generation,
            "population_size": len(results),
            "feasible_count": len(feasible),
            "archive_size": len(archive),
            "generation_wall_time_s": generation_wall_time_s,
            "evaluator_eval_count": evaluator_eval_count,
            "num_fast_evaluated": int(fast_eval_count),
            "num_trigger_fine_eval": int(recheck_eval_count),
            "fine_eval_trigger_rate": float(recheck_eval_count) / max(len(results), 1),
            "population_diversity": self._population_diversity(population_vectors),
            "mutation_rate": float(self.config.mutation_rate),
            "reinitialize_ratio": float(self.config.reinit_fraction),
        }

        if feasible:
            npvs = [
                r.lifecycle_financial_result.npv_yuan
                for r in feasible
                if r.lifecycle_financial_result is not None
            ]
            paybacks = [
                (
                    r.lifecycle_financial_result.simple_payback_years
                    if r.lifecycle_financial_result is not None
                    and r.lifecycle_financial_result.simple_payback_years is not None
                    else np.nan
                )
                for r in feasible
            ]
            investments = [
                r.lifecycle_financial_result.initial_investment_yuan
                for r in feasible
                if r.lifecycle_financial_result is not None
            ]

            record["best_npv_yuan"] = float(np.max(npvs)) if npvs else np.nan
            record["avg_npv_yuan"] = float(np.mean(npvs)) if npvs else np.nan
            valid_paybacks = []
            for payback in paybacks:
                try:
                    value = float(payback)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value):
                    valid_paybacks.append(value)
            record["best_payback_years"] = min(valid_paybacks) if valid_paybacks else np.nan
            record["avg_investment_yuan"] = float(np.mean(investments)) if investments else np.nan
        else:
            record["best_npv_yuan"] = np.nan
            record["avg_npv_yuan"] = np.nan
            record["best_payback_years"] = np.nan
            record["avg_investment_yuan"] = np.nan

        if best_compromise is not None:
            record["best_compromise"] = best_compromise.summary_dict()
            best_cost = self._best_compromise_cost(archive, best_compromise)
            record["best_compromise_cost"] = best_cost
            prev_cost = _finite_float(previous_best_compromise_cost)
            if prev_cost is not None and np.isfinite(best_cost):
                record["pareto_improvement_rate"] = abs(best_cost - prev_cost) / max(abs(prev_cost), 1e-9)
            else:
                record["pareto_improvement_rate"] = np.nan
        else:
            record["best_compromise_cost"] = np.nan

        record["adaptive_signal"] = self._adaptive_signal(record)
        record["population_adjust_reason"] = self._adaptive_reason(record)

        return record

    def _best_compromise_cost(
        self,
        archive: list[FitnessEvaluationResult],
        best_compromise: FitnessEvaluationResult,
    ) -> float:
        feasible = [result for result in archive if result.feasible]
        if not feasible:
            return float("nan")
        costs = self._weighted_compromise_costs(feasible)
        return float(costs.get(id(best_compromise), np.nan))

    def _adaptive_signal(self, record: dict[str, Any]) -> float:
        cfg = self.config
        improvement = float(record.get("pareto_improvement_rate", np.nan))
        if not np.isfinite(improvement):
            improvement = cfg.adaptive_target_improve
        diversity = float(record.get("population_diversity", np.nan))
        if not np.isfinite(diversity):
            diversity = cfg.adaptive_target_diversity
        recheck_rate = float(record.get("fine_eval_trigger_rate", 0.0) or 0.0)
        return float(
            cfg.adaptive_weight_stagnation
            * np.tanh((cfg.adaptive_target_improve - improvement) / max(cfg.adaptive_scale_improve, 1e-9))
            + cfg.adaptive_weight_diversity
            * np.tanh((cfg.adaptive_target_diversity - diversity) / max(cfg.adaptive_scale_diversity, 1e-9))
            - cfg.adaptive_weight_recheck_rate
            * np.tanh((recheck_rate - cfg.adaptive_target_recheck_rate) / max(cfg.adaptive_scale_recheck_rate, 1e-9))
        )

    def _adaptive_reason(self, record: dict[str, Any]) -> str:
        signal = float(record.get("adaptive_signal", 0.0) or 0.0)
        recheck_rate = float(record.get("fine_eval_trigger_rate", 0.0) or 0.0)
        if recheck_rate > self.config.adaptive_recheck_rate_force_shrink:
            return "fine_eval_rate_too_high_force_shrink"
        if recheck_rate > self.config.adaptive_recheck_rate_block_growth:
            return "fine_eval_rate_high_block_growth"
        if signal > self.config.adaptive_signal_growth_threshold:
            return "stagnation_or_low_diversity_expand"
        if signal < self.config.adaptive_signal_shrink_threshold:
            return "active_progress_or_high_diversity_shrink"
        return "stable"

    @staticmethod
    def _population_diversity(population_vectors: list[np.ndarray] | None) -> float:
        if not population_vectors:
            return float("nan")
        arr = np.asarray(population_vectors, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 2:
            return 0.0
        parts: list[float] = []
        for col in (0, 1):
            values = arr[:, col]
            span = float(np.max(values) - np.min(values))
            parts.append(0.0 if span <= 1e-12 else float(np.std(values) / span))
        return float(sum(parts))

    def _evaluator_counter(self, name: str) -> int:
        evaluator = getattr(self.bridge, "evaluator", None)
        try:
            return int(getattr(evaluator, name, 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _print_generation_record(record: dict[str, Any]) -> None:
        logger.info("-" * 72)
        logger.info(
            "优化迭代 %s | 种群=%s | 可行解=%s | Archive=%s",
            record['generation'],
            record['population_size'],
            record['feasible_count'],
            record['archive_size'],
        )
        logger.info(
            "  最优NPV=%.2f | 平均NPV=%.2f | 最优回收期=%.2f | 平均投资=%.2f",
            record['best_npv_yuan'],
            record['avg_npv_yuan'],
            record['best_payback_years'],
            record['avg_investment_yuan'],
        )
