from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

DEFAULT_ECONOMIC_METRIC_WEIGHTS = {
    "npv": 0.45,
    "irr": 0.20,
    "payback": 0.25,
    "investment": 0.10,
}
DEFAULT_SAFETY_METRIC_WEIGHTS = {
    "transformer": 0.25,
    "voltage": 0.25,
    "line": 0.25,
    "cycle": 0.25,
}
DEFAULT_DEVICE_SAFETY_BETA = 0.5


@dataclass(slots=True)
class WeightedObjectiveScores:
    economic_cost: np.ndarray
    operation_safety_cost: np.ndarray
    device_safety_cost: np.ndarray
    safety_cost: np.ndarray
    compromise_cost: np.ndarray
    economic_score: np.ndarray
    operation_safety_score: np.ndarray
    device_safety_score: np.ndarray
    safety_score: np.ndarray
    fitness_score: np.ndarray
    economic_metric_costs: dict[str, np.ndarray]
    economic_metric_scores: dict[str, np.ndarray]
    safety_metric_costs: dict[str, np.ndarray]
    safety_metric_scores: dict[str, np.ndarray]
    economic_metric_weights: dict[str, float]
    safety_metric_weights: dict[str, float]
    economic_weight: float
    safety_weight: float
    device_safety_beta: float


def compute_weighted_objective_scores(
    *,
    npv: Sequence[float],
    irr: Sequence[float],
    payback: Sequence[float],
    investment: Sequence[float],
    transformer: Sequence[float],
    voltage: Sequence[float],
    line: Sequence[float],
    cycle: Sequence[float],
    safety_economy_tradeoff: float = 0.5,
    economic_metric_weights: Mapping[str, float] | None = None,
    safety_metric_weights: Mapping[str, float] | None = None,
    device_safety_cost: Sequence[float] | None = None,
    device_safety_beta: float = DEFAULT_DEVICE_SAFETY_BETA,
) -> WeightedObjectiveScores:
    """Return cost and display-score views for the same weighted objective.

    Internally, lower costs are better. Externally, higher scores are better.
    The ``cycle`` input is the continuous device-strategy safety metric, usually
    annual equivalent full cycles; hard cycle/duration violations are only a
    fallback when richer operation data is unavailable.
    """
    econ_weights = normalize_weights(economic_metric_weights, DEFAULT_ECONOMIC_METRIC_WEIGHTS)
    safety_weights = normalize_weights(safety_metric_weights, DEFAULT_SAFETY_METRIC_WEIGHTS)
    safety_weight = min(max(float(safety_economy_tradeoff), 0.0), 1.0)
    economic_weight = 1.0 - safety_weight
    n_items = len(_array(npv))

    economic_metric_costs = {
        "npv": normalize_cost_values(-_array(npv)),
        "irr": normalize_cost_values(-_array(irr)),
        "payback": normalize_cost_values(_array(payback)),
        "investment": normalize_cost_values(_array(investment)),
    }
    safety_metric_costs = {
        "transformer": normalize_cost_values(_array(transformer)),
        "voltage": normalize_cost_values(_array(voltage)),
        "line": normalize_cost_values(_array(line)),
        "cycle": normalize_cost_values(_array(cycle)),
    }

    economic_cost = sum(
        econ_weights[key] * economic_metric_costs[key]
        for key in DEFAULT_ECONOMIC_METRIC_WEIGHTS
    )
    operation_safety_cost = sum(
        safety_weights[key] * safety_metric_costs[key]
        for key in DEFAULT_SAFETY_METRIC_WEIGHTS
    )
    device_cost, effective_device_beta = _device_safety_cost_array(
        device_safety_cost,
        n_items=n_items,
        beta=device_safety_beta,
    )
    if effective_device_beta > 0.0:
        safety_cost = (
            (1.0 - effective_device_beta) * operation_safety_cost
            + effective_device_beta * device_cost
        )
    else:
        safety_cost = operation_safety_cost.copy()
    compromise_cost = economic_weight * economic_cost + safety_weight * safety_cost

    return WeightedObjectiveScores(
        economic_cost=economic_cost,
        operation_safety_cost=operation_safety_cost,
        device_safety_cost=device_cost,
        safety_cost=safety_cost,
        compromise_cost=compromise_cost,
        economic_score=score_from_cost(economic_cost),
        operation_safety_score=score_from_cost(operation_safety_cost),
        device_safety_score=score_from_cost(device_cost),
        safety_score=score_from_cost(safety_cost),
        fitness_score=score_from_cost(compromise_cost),
        economic_metric_costs=economic_metric_costs,
        economic_metric_scores={key: score_from_cost(value) for key, value in economic_metric_costs.items()},
        safety_metric_costs=safety_metric_costs,
        safety_metric_scores={key: score_from_cost(value) for key, value in safety_metric_costs.items()},
        economic_metric_weights=econ_weights,
        safety_metric_weights=safety_weights,
        economic_weight=economic_weight,
        safety_weight=safety_weight,
        device_safety_beta=effective_device_beta,
    )


def score_from_cost(cost: np.ndarray) -> np.ndarray:
    return np.clip(1.0 - np.asarray(cost, dtype=float), 0.0, 1.0)


def normalize_cost_values(values: Sequence[float] | np.ndarray) -> np.ndarray:
    arr = _array(values)
    if arr.size == 0:
        return arr
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros_like(arr)
    lo = float(np.min(arr[finite]))
    hi = float(np.max(arr[finite]))
    if hi - lo <= 1e-12:
        return np.zeros_like(arr)
    return np.nan_to_num((arr - lo) / (hi - lo), nan=1.0, posinf=1.0, neginf=0.0)


def normalize_weights(
    supplied: Mapping[str, float] | None,
    defaults: Mapping[str, float],
) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, default in defaults.items():
        try:
            raw = float((supplied or {}).get(key, default))
        except Exception:
            raw = float(default)
        values[key] = max(0.0, raw) if np.isfinite(raw) else 0.0
    total = sum(values.values())
    if total <= 1e-12:
        fallback_total = sum(float(value) for value in defaults.values())
        return {key: float(value) / fallback_total for key, value in defaults.items()}
    return {key: value / total for key, value in values.items()}


def _array(values: Sequence[float] | np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _device_safety_cost_array(
    values: Sequence[float] | None,
    *,
    n_items: int,
    beta: float,
) -> tuple[np.ndarray, float]:
    if values is None:
        return np.full(n_items, np.nan, dtype=float), 0.0
    arr = _array(values)
    if arr.size != n_items:
        raise ValueError(f"device_safety_cost 长度应为 {n_items}，当前为 {arr.size}")
    finite = np.isfinite(arr)
    if not finite.any():
        return np.full(n_items, np.nan, dtype=float), 0.0
    arr = np.nan_to_num(arr, nan=0.5, posinf=1.0, neginf=0.0)
    arr = np.clip(arr, 0.0, 1.0)
    effective_beta = min(max(float(beta), 0.0), 1.0)
    if effective_beta <= 1e-12:
        return arr, 0.0
    return arr, effective_beta


def device_strategy_safety_metric(result: object) -> float:
    """Return the continuous device-strategy safety input for one result.

    Prefer annual equivalent full cycles because it differentiates feasible
    candidates before they exceed a hard cycle limit. ``obj_safety`` is kept as a
    fallback for legacy objects and summaries that only expose the old proxy.
    """

    annual_result = getattr(result, "annual_operation_result", None)
    if annual_result is not None:
        annual_cycles = _finite_optional(getattr(annual_result, "annual_equivalent_full_cycles", None))
        if annual_cycles is not None:
            return annual_cycles

    objective_vector = getattr(result, "objective_vector", None)
    if objective_vector is not None:
        objective_safety = _finite_optional(getattr(objective_vector, "obj_safety", None))
        if objective_safety is not None:
            return objective_safety

    constraint_vector = getattr(result, "constraint_vector", None)
    if constraint_vector is None:
        return 0.0
    cycle_violation = _finite_optional(getattr(constraint_vector, "cycle_violation", None)) or 0.0
    duration_violation = _finite_optional(getattr(constraint_vector, "duration_violation_h", None)) or 0.0
    return cycle_violation + duration_violation


def device_safety_cost_metric(result: object) -> float | None:
    metadata = getattr(result, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    if not _truthy(metadata.get("device_safety_available")):
        return None
    return _finite_optional(metadata.get("device_safety_cost"))


def annotate_dataframe_scores(
    df: pd.DataFrame,
    *,
    safety_economy_tradeoff: float = 0.5,
    economic_metric_weights: Mapping[str, float] | None = None,
    safety_metric_weights: Mapping[str, float] | None = None,
    device_safety_beta: float = DEFAULT_DEVICE_SAFETY_BETA,
) -> pd.DataFrame:
    """Annotate a results DataFrame with pre-computed fitness scores.

    Columns added: fitness_score, fitness_score_pct, compromise_cost,
    economic_cost, safety_cost, economic_score, safety_score,
    and per-metric cost/score columns.

    The DataFrame is expected to have been produced by
    ``OptimizerBridge.results_to_dataframe`` (i.e. ``summary_dict()`` rows).
    """
    out = df.copy()
    if out.empty:
        for col in _SCORE_COLUMNS:
            out[col] = []
        return out

    feasible_mask = out.get("feasible")
    if feasible_mask is None:
        feasible_mask = pd.Series([True] * len(out), index=out.index)
    feasible_mask = feasible_mask.astype(bool)

    if not feasible_mask.any():
        # No feasible solutions – fall back to violation-based scoring.
        _annotate_infeasible_fallback(out)
        return out

    feasible_idx = out.index[feasible_mask]
    scored = out.loc[feasible_idx]

    invest = scored.get("initial_investment_yuan", pd.Series([0.0] * len(scored), index=scored.index)).fillna(0.0).to_numpy(dtype=float)
    npv = scored.get("npv_yuan", pd.Series([0.0] * len(scored), index=scored.index)).fillna(0.0).to_numpy(dtype=float)

    irr_raw = scored.get("irr", pd.Series([np.nan] * len(scored), index=scored.index))
    irr = np.where(irr_raw.notna().to_numpy(), irr_raw.to_numpy(dtype=float), 0.0)

    payback_raw = scored.get("simple_payback_years", pd.Series([np.nan] * len(scored), index=scored.index))
    payback = np.where(
        payback_raw.notna().to_numpy(),
        payback_raw.to_numpy(dtype=float),
        scored.get("obj_payback", pd.Series([99.0] * len(scored), index=scored.index)).to_numpy(dtype=float),
    )

    transformer = scored.get("transformer_violation_hours", pd.Series([0.0] * len(scored), index=scored.index)).fillna(0.0).to_numpy(dtype=float)
    voltage = scored.get("voltage_violation_pu", pd.Series([0.0] * len(scored), index=scored.index)).fillna(0.0).to_numpy(dtype=float)
    line = scored.get("line_loading_violation_pct", pd.Series([0.0] * len(scored), index=scored.index)).fillna(0.0).to_numpy(dtype=float)
    cycle = _device_strategy_values(scored)
    device_safety = _device_safety_values(scored)

    scores = compute_weighted_objective_scores(
        npv=npv,
        irr=irr,
        payback=payback,
        investment=invest,
        transformer=transformer,
        voltage=voltage,
        line=line,
        cycle=cycle,
        safety_economy_tradeoff=safety_economy_tradeoff,
        economic_metric_weights=economic_metric_weights,
        safety_metric_weights=safety_metric_weights,
        device_safety_cost=device_safety,
        device_safety_beta=device_safety_beta,
    )

    _apply_scores_to_dataframe(out, feasible_idx, scores)
    return out


def _device_strategy_values(scored: pd.DataFrame) -> np.ndarray:
    annual_cycles = _first_numeric_series(
        scored,
        ("annual_equivalent_full_cycles", "equivalent_full_cycles", "annualCycles"),
    )
    objective_safety = _first_numeric_series(scored, ("obj_safety", "objectiveSafety"))
    cycle_violation = _numeric_series(scored, "cycle_violation", 0.0)
    duration_violation = _numeric_series(scored, "duration_violation_h", 0.0)
    violation_fallback = cycle_violation + duration_violation

    if annual_cycles is not None:
        values = annual_cycles.copy()
        if objective_safety is not None:
            values = values.fillna(objective_safety)
        values = values.fillna(pd.Series(violation_fallback, index=scored.index))
        return values.fillna(0.0).to_numpy(dtype=float)
    if objective_safety is not None:
        values = objective_safety.fillna(pd.Series(violation_fallback, index=scored.index))
        return values.fillna(0.0).to_numpy(dtype=float)
    return violation_fallback


def _device_safety_values(scored: pd.DataFrame) -> np.ndarray | None:
    device_costs = _first_numeric_series(scored, ("device_safety_cost", "deviceSafetyCost"))
    if device_costs is None:
        return None

    available_raw = None
    for column in ("device_safety_available", "deviceSafetyAvailable"):
        if column in scored:
            available_raw = scored[column]
            break
    if available_raw is not None:
        available = available_raw.map(_truthy).fillna(False)
        if not available.any():
            return None
        values = device_costs.where(available, np.nan)
        return values.to_numpy(dtype=float)

    return device_costs.to_numpy(dtype=float)


def _first_numeric_series(
    df: pd.DataFrame,
    columns: Sequence[str],
) -> pd.Series | None:
    for column in columns:
        if column not in df:
            continue
        series = pd.to_numeric(df[column], errors="coerce")
        if series.notna().any():
            return series
    return None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)) and np.isfinite(float(value)):
        return bool(int(value))
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on", "是", "启用", "available"}


def _numeric_series(df: pd.DataFrame, column: str, default: float) -> np.ndarray:
    if column not in df:
        return np.full(len(df), float(default), dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(float(default)).to_numpy(dtype=float)


def _finite_optional(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


_SCORE_COLUMNS = [
    "fitness_score", "fitness_score_pct", "compromise_cost",
    "economic_cost", "operation_safety_cost", "device_safety_cost", "safety_cost",
    "economic_score", "operation_safety_score", "device_safety_score", "safety_score",
    "economic_score_pct", "operation_safety_score_pct", "device_safety_score_pct", "safety_score_pct",
    "device_safety_beta",
    "objective_npv_cost", "objective_irr_cost", "objective_payback_cost", "objective_investment_cost",
    "objective_transformer_cost", "objective_voltage_cost", "objective_line_cost", "objective_cycle_cost",
    "objective_npv_score_pct", "objective_irr_score_pct", "objective_payback_score_pct", "objective_investment_score_pct",
    "objective_transformer_score_pct", "objective_voltage_score_pct", "objective_line_score_pct", "objective_cycle_score_pct",
]


def _apply_scores_to_dataframe(
    df: pd.DataFrame,
    scored_index: pd.Index,
    scores: WeightedObjectiveScores,
) -> None:
    df["fitness_score"] = np.nan
    df["fitness_score_pct"] = np.nan
    df["compromise_cost"] = np.nan
    df["economic_cost"] = np.nan
    df["operation_safety_cost"] = np.nan
    df["device_safety_cost"] = np.nan
    df["safety_cost"] = np.nan
    df["economic_score"] = np.nan
    df["operation_safety_score"] = np.nan
    df["device_safety_score"] = np.nan
    df["safety_score"] = np.nan
    df["economic_score_pct"] = np.nan
    df["operation_safety_score_pct"] = np.nan
    df["device_safety_score_pct"] = np.nan
    df["safety_score_pct"] = np.nan
    df["device_safety_beta"] = np.nan
    df["objective_npv_cost"] = np.nan
    df["objective_irr_cost"] = np.nan
    df["objective_payback_cost"] = np.nan
    df["objective_investment_cost"] = np.nan
    df["objective_transformer_cost"] = np.nan
    df["objective_voltage_cost"] = np.nan
    df["objective_line_cost"] = np.nan
    df["objective_cycle_cost"] = np.nan
    df["objective_npv_score_pct"] = np.nan
    df["objective_irr_score_pct"] = np.nan
    df["objective_payback_score_pct"] = np.nan
    df["objective_investment_score_pct"] = np.nan
    df["objective_transformer_score_pct"] = np.nan
    df["objective_voltage_score_pct"] = np.nan
    df["objective_line_score_pct"] = np.nan
    df["objective_cycle_score_pct"] = np.nan

    df.loc[scored_index, "fitness_score"] = scores.fitness_score
    df.loc[scored_index, "fitness_score_pct"] = scores.fitness_score * 100.0
    df.loc[scored_index, "compromise_cost"] = scores.compromise_cost
    df.loc[scored_index, "economic_cost"] = scores.economic_cost
    df.loc[scored_index, "operation_safety_cost"] = scores.operation_safety_cost
    df.loc[scored_index, "device_safety_cost"] = scores.device_safety_cost
    df.loc[scored_index, "safety_cost"] = scores.safety_cost
    df.loc[scored_index, "economic_score"] = scores.economic_score
    df.loc[scored_index, "operation_safety_score"] = scores.operation_safety_score
    df.loc[scored_index, "device_safety_score"] = scores.device_safety_score
    df.loc[scored_index, "safety_score"] = scores.safety_score
    df.loc[scored_index, "economic_score_pct"] = scores.economic_score * 100.0
    df.loc[scored_index, "operation_safety_score_pct"] = scores.operation_safety_score * 100.0
    df.loc[scored_index, "device_safety_score_pct"] = scores.device_safety_score * 100.0
    df.loc[scored_index, "safety_score_pct"] = scores.safety_score * 100.0
    df.loc[scored_index, "device_safety_beta"] = scores.device_safety_beta
    df.loc[scored_index, "objective_npv_cost"] = scores.economic_metric_costs["npv"]
    df.loc[scored_index, "objective_irr_cost"] = scores.economic_metric_costs["irr"]
    df.loc[scored_index, "objective_payback_cost"] = scores.economic_metric_costs["payback"]
    df.loc[scored_index, "objective_investment_cost"] = scores.economic_metric_costs["investment"]
    df.loc[scored_index, "objective_transformer_cost"] = scores.safety_metric_costs["transformer"]
    df.loc[scored_index, "objective_voltage_cost"] = scores.safety_metric_costs["voltage"]
    df.loc[scored_index, "objective_line_cost"] = scores.safety_metric_costs["line"]
    df.loc[scored_index, "objective_cycle_cost"] = scores.safety_metric_costs["cycle"]
    df.loc[scored_index, "objective_npv_score_pct"] = scores.economic_metric_scores["npv"] * 100.0
    df.loc[scored_index, "objective_irr_score_pct"] = scores.economic_metric_scores["irr"] * 100.0
    df.loc[scored_index, "objective_payback_score_pct"] = scores.economic_metric_scores["payback"] * 100.0
    df.loc[scored_index, "objective_investment_score_pct"] = scores.economic_metric_scores["investment"] * 100.0
    df.loc[scored_index, "objective_transformer_score_pct"] = scores.safety_metric_scores["transformer"] * 100.0
    df.loc[scored_index, "objective_voltage_score_pct"] = scores.safety_metric_scores["voltage"] * 100.0
    df.loc[scored_index, "objective_line_score_pct"] = scores.safety_metric_scores["line"] * 100.0
    df.loc[scored_index, "objective_cycle_score_pct"] = scores.safety_metric_scores["cycle"] * 100.0


def _annotate_infeasible_fallback(df: pd.DataFrame) -> None:
    violation = df.get("total_violation", pd.Series([0.0] * len(df), index=df.index)).fillna(0.0).to_numpy(dtype=float)
    finite = np.isfinite(violation)
    if not finite.any():
        costs = np.zeros(len(df))
    else:
        lo = float(np.min(violation[finite]))
        hi = float(np.max(violation[finite]))
        if hi - lo <= 1e-12:
            costs = np.zeros(len(df))
        else:
            costs = np.clip((violation - lo) / (hi - lo), 0.0, 1.0)

    for column in _SCORE_COLUMNS:
        df[column] = np.nan

    fitness = 1.0 - costs
    df["fitness_score"] = fitness
    df["fitness_score_pct"] = fitness * 100.0
    df["compromise_cost"] = costs
    df["economic_cost"] = np.nan
    df["safety_cost"] = costs
    df["economic_score"] = np.nan
    df["safety_score"] = fitness
    df["economic_score_pct"] = np.nan
    df["safety_score_pct"] = fitness * 100.0
