from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

from storage_engine_project.optimization.objective_scoring import (
    DEFAULT_DEVICE_SAFETY_BETA,
    compute_weighted_objective_scores,
    device_safety_cost_metric,
    device_strategy_safety_metric,
)
from storage_engine_project.optimization.optimization_models import FitnessEvaluationResult


def dominates(a: FitnessEvaluationResult, b: FitnessEvaluationResult) -> bool:
    a_feasible = a.feasible
    b_feasible = b.feasible

    if a_feasible and (not b_feasible):
        return True
    if (not a_feasible) and b_feasible:
        return False

    if (not a_feasible) and (not b_feasible):
        return a.constraint_vector.total_violation() < b.constraint_vector.total_violation()

    a_obj = a.objective_vector.as_tuple()
    b_obj = b.objective_vector.as_tuple()

    all_not_worse = all(x <= y for x, y in zip(a_obj, b_obj))
    one_strictly_better = any(x < y for x, y in zip(a_obj, b_obj))
    return all_not_worse and one_strictly_better


def update_archive(
    archive: list[FitnessEvaluationResult],
    candidates: Iterable[FitnessEvaluationResult],
) -> list[FitnessEvaluationResult]:
    out = list(archive)

    for cand in candidates:
        dominated_by_archive = any(dominates(a, cand) for a in out)
        if dominated_by_archive:
            continue

        out = [a for a in out if not dominates(cand, a)]
        if not any(_same_solution(a, cand) for a in out):
            out.append(cand)

    return out


def select_best_compromise(
    archive: list[FitnessEvaluationResult],
    safety_economy_tradeoff: float = 0.5,
    economic_metric_weights: Mapping[str, float] | None = None,
    safety_metric_weights: Mapping[str, float] | None = None,
    device_safety_beta: float = DEFAULT_DEVICE_SAFETY_BETA,
) -> FitnessEvaluationResult | None:
    if not archive:
        return None

    feasible = [x for x in archive if x.feasible]
    if not feasible:
        return min(archive, key=lambda x: x.constraint_vector.total_violation())
    if len(feasible) == 1:
        return feasible[0]

    invest = np.array([_investment_metric(x) for x in feasible], dtype=float)
    npv = np.array([_npv_metric(x) for x in feasible], dtype=float)
    irr = np.array([_irr_metric(x) for x in feasible], dtype=float)
    payback = np.array([_payback_metric(x) for x in feasible], dtype=float)

    scores = compute_weighted_objective_scores(
        npv=npv,
        irr=irr,
        payback=payback,
        investment=invest,
        transformer=np.array([x.constraint_vector.transformer_violation_hours for x in feasible], dtype=float),
        voltage=np.array([x.constraint_vector.voltage_violation_pu for x in feasible], dtype=float),
        line=np.array([x.constraint_vector.line_loading_violation_pct for x in feasible], dtype=float),
        cycle=np.array([device_strategy_safety_metric(x) for x in feasible], dtype=float),
        safety_economy_tradeoff=safety_economy_tradeoff,
        economic_metric_weights=economic_metric_weights,
        safety_metric_weights=safety_metric_weights,
        device_safety_cost=_device_safety_costs(feasible),
        device_safety_beta=device_safety_beta,
    )
    best_idx = int(np.argmin(scores.compromise_cost))
    return feasible[best_idx]


def _same_solution(a: FitnessEvaluationResult, b: FitnessEvaluationResult) -> bool:
    da = a.decision
    db = b.decision
    return (
        da.strategy_id == db.strategy_id
        and abs(da.rated_power_kw - db.rated_power_kw) <= 1e-9
        and abs(da.rated_energy_kwh - db.rated_energy_kwh) <= 1e-9
    )


def _device_safety_costs(results: list[FitnessEvaluationResult]) -> list[float] | None:
    costs = [device_safety_cost_metric(result) for result in results]
    if not any(cost is not None for cost in costs):
        return None
    return [float(cost) if cost is not None else float("nan") for cost in costs]


def _investment_metric(result: FitnessEvaluationResult) -> float:
    financial = result.lifecycle_financial_result
    if financial is not None:
        return float(financial.initial_investment_yuan)
    return float(result.objective_vector.obj_investment)


def _npv_metric(result: FitnessEvaluationResult) -> float:
    financial = result.lifecycle_financial_result
    if financial is not None:
        return float(financial.npv_yuan)
    return -float(result.objective_vector.obj_npv)


def _irr_metric(result: FitnessEvaluationResult) -> float:
    financial = result.lifecycle_financial_result
    if financial is not None and financial.irr is not None:
        return float(financial.irr)
    return 0.0


def _payback_metric(result: FitnessEvaluationResult) -> float:
    financial = result.lifecycle_financial_result
    if financial is not None and financial.simple_payback_years is not None:
        return float(financial.simple_payback_years)
    return float(result.objective_vector.obj_payback)
