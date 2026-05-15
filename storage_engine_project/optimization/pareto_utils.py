from __future__ import annotations

from typing import Iterable

import numpy as np

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
) -> FitnessEvaluationResult | None:
    if not archive:
        return None

    feasible = [x for x in archive if x.feasible]
    if not feasible:
        return min(archive, key=lambda x: x.constraint_vector.total_violation())
    if len(feasible) == 1:
        return feasible[0]

    invest = np.array([x.lifecycle_financial_result.initial_investment_yuan for x in feasible], dtype=float)
    npv = np.array([x.lifecycle_financial_result.npv_yuan for x in feasible], dtype=float)
    payback = np.array([
        float(x.lifecycle_financial_result.simple_payback_years)
        if x.lifecycle_financial_result.simple_payback_years is not None else 99.0
        for x in feasible
    ], dtype=float)
    safety = np.array([float(x.objective_vector.obj_safety) for x in feasible], dtype=float)

    idx_min_invest = int(np.argmin(invest))
    idx_max_npv = int(np.argmax(npv))
    p0 = np.array([invest[idx_min_invest], npv[idx_min_invest]], dtype=float)
    p1 = np.array([invest[idx_max_npv], npv[idx_max_npv]], dtype=float)

    if np.allclose(p0, p1):
        return min(
            feasible,
            key=lambda x: (
                _normalize_scalar(x.lifecycle_financial_result.simple_payback_years, payback),
                _normalize_scalar(x.objective_vector.obj_safety, safety),
                _normalize_scalar(-x.lifecycle_financial_result.npv_yuan, -npv),
            ),
        )

    distances = []
    line_vec = p1 - p0
    denom = np.linalg.norm(line_vec)
    for inv, n in zip(invest, npv):
        p = np.array([inv, n], dtype=float)
        dist = abs(np.cross(line_vec, p - p0)) / max(denom, 1e-12)
        distances.append(float(dist))
    distances = np.asarray(distances, dtype=float)

    dist_norm = _normalize_array(distances, reverse=True)
    payback_norm = _normalize_array(payback, reverse=False)
    safety_norm = _normalize_array(safety, reverse=False)
    npv_norm = _normalize_array(-npv, reverse=False)

    s = float(safety_economy_tradeoff)
    dist_w = 0.45 - 0.15 * s
    payback_w = 0.35 - 0.30 * s
    safety_w = 0.00 + 0.50 * s
    npv_w = 0.20 - 0.15 * s
    scores = dist_w * dist_norm + payback_w * payback_norm + safety_w * safety_norm + npv_w * npv_norm
    best_idx = int(np.argmin(scores))
    return feasible[best_idx]


def _same_solution(a: FitnessEvaluationResult, b: FitnessEvaluationResult) -> bool:
    da = a.decision
    db = b.decision
    return (
        da.strategy_id == db.strategy_id
        and abs(da.rated_power_kw - db.rated_power_kw) <= 1e-9
        and abs(da.rated_energy_kwh - db.rated_energy_kwh) <= 1e-9
    )


def _normalize_array(x: np.ndarray, reverse: bool = False) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    lo = float(np.min(x))
    hi = float(np.max(x))
    if hi - lo <= 1e-12:
        out = np.zeros_like(x)
    else:
        out = (x - lo) / (hi - lo)
    if reverse:
        out = 1.0 - out
    return out


def _normalize_scalar(value: float | None, ref: np.ndarray) -> float:
    if value is None:
        return 1.0
    arr = np.asarray(ref, dtype=float).reshape(-1)
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if hi - lo <= 1e-12:
        return 0.0
    return float((float(value) - lo) / (hi - lo))
