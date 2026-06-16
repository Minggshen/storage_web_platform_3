from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from storage_engine_project.optimization.lemming_optimizer import LemmingOptimizationRunResult
from storage_engine_project.optimization.objective_scoring import annotate_dataframe_scores
from storage_engine_project.visualization.mpl_global import setup_matplotlib_chinese

_COLORS = {
    "npv": "#2563eb",
    "cashflow": "#16a34a",
    "payback": "#ea580c",
    "discounted": "#9a3412",
    "fitness": "#059669",
    "best": "#dc2626",
    "grid": "#cbd5e1",
}

def _ensure_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _safe_name(name: str) -> str:
    invalid = '<>:"/\\|?*'
    out = str(name).strip()
    for ch in invalid:
        out = out.replace(ch, "_")
    return out.replace(" ", "_")


def _finite_float(value: Any, default: float = np.nan) -> float:
    try:
        if value in (None, ""):
            return float(default)
        number = float(value)
    except Exception:
        return float(default)
    return number if np.isfinite(number) else float(default)


def _records(run_result: LemmingOptimizationRunResult) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in run_result.archive_results:
        row = result.summary_dict()
        row.setdefault("initial_investment_yuan", row.get("obj_investment"))
        row.setdefault("npv_yuan", -_finite_float(row.get("obj_npv")))
        row.setdefault("simple_payback_years", row.get("obj_payback"))
        row.setdefault("discounted_payback_years", row.get("obj_payback"))
        row.setdefault("annualized_net_cashflow_yuan", np.nan)
        row["feasible"] = bool(result.feasible)
        row["total_violation"] = float(result.constraint_vector.total_violation())
        row["transformer_violation_hours"] = float(result.constraint_vector.transformer_violation_hours)
        row["voltage_violation_pu"] = float(result.constraint_vector.voltage_violation_pu)
        row["line_loading_violation_pct"] = float(result.constraint_vector.line_loading_violation_pct)
        row["cycle_violation"] = float(result.constraint_vector.cycle_violation)
        row["duration_violation_h"] = float(result.constraint_vector.duration_violation_h)
        row["device_strategy_violation"] = float(
            result.constraint_vector.cycle_violation + result.constraint_vector.duration_violation_h
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _annotate_fitness(
    df: pd.DataFrame,
    safety_economy_tradeoff: float,
    economic_metric_weights: Mapping[str, float] | None,
    safety_metric_weights: Mapping[str, float] | None,
    device_safety_beta: float,
) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    out = annotate_dataframe_scores(
        out,
        safety_economy_tradeoff=safety_economy_tradeoff,
        economic_metric_weights=economic_metric_weights,
        safety_metric_weights=safety_metric_weights,
        device_safety_beta=device_safety_beta,
    )
    scored = out[pd.to_numeric(out.get("fitness_score"), errors="coerce").notna()]
    out["objective_best"] = False
    if scored.empty:
        return out
    best_idx = pd.to_numeric(scored["fitness_score"], errors="coerce").idxmax()
    out.loc[best_idx, "objective_best"] = True
    return out


def _apply_style(ax: plt.Axes, ylabel: str | None = None, xlabel: str | None = None) -> None:
    ax.grid(True, color=_COLORS["grid"], linestyle="--", linewidth=0.6, alpha=0.45)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)


def plot_investment_economics_trends(
    case_name: str,
    run_result: LemmingOptimizationRunResult,
    output_dir: str | Path,
    *,
    safety_economy_tradeoff: float = 0.5,
    economic_metric_weights: Mapping[str, float] | None = None,
    safety_metric_weights: Mapping[str, float] | None = None,
    device_safety_beta: float = 0.5,
) -> list[str]:
    setup_matplotlib_chinese()
    out_dir = _ensure_dir(output_dir)
    df = _records(run_result)
    if df.empty:
        return []
    work = _annotate_fitness(
        df,
        safety_economy_tradeoff,
        economic_metric_weights,
        safety_metric_weights,
        device_safety_beta,
    )
    work = work.sort_values(["initial_investment_yuan", "npv_yuan"], kind="stable")
    for column in (
        "initial_investment_yuan",
        "npv_yuan",
        "annualized_net_cashflow_yuan",
        "simple_payback_years",
        "discounted_payback_years",
        "fitness_score_pct",
    ):
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=["initial_investment_yuan"])
    if work.empty:
        return []

    x = work["initial_investment_yuan"].to_numpy(dtype=float) / 10000.0
    fig, axes = plt.subplots(2, 1, figsize=(10.8, 8.4), sharex=True)
    fig.suptitle(f"{case_name}：投资变化下经济指标与适应度", fontsize=14, fontweight="bold", y=0.992)

    ax = axes[0]
    ax.plot(x, work["npv_yuan"].to_numpy(dtype=float) / 10000.0, marker="o", color=_COLORS["npv"], label="NPV")
    if "annualized_net_cashflow_yuan" in work.columns and work["annualized_net_cashflow_yuan"].notna().any():
        ax.plot(
            x,
            work["annualized_net_cashflow_yuan"].to_numpy(dtype=float) / 10000.0,
            marker="s",
            color=_COLORS["cashflow"],
            label="年净现金流",
        )
    ax.axhline(0, color="#ef4444", linestyle="--", linewidth=1.0, label="0")
    _apply_style(ax, ylabel="金额 / 万元")
    ax.set_title("收益指标随初始投资变化")
    ax.legend(loc="best")

    ax = axes[1]
    if "simple_payback_years" in work.columns and work["simple_payback_years"].notna().any():
        ax.plot(x, work["simple_payback_years"].to_numpy(dtype=float), marker="o", color=_COLORS["payback"], label="静态回收期")
    if "discounted_payback_years" in work.columns and work["discounted_payback_years"].notna().any():
        ax.plot(
            x,
            work["discounted_payback_years"].to_numpy(dtype=float),
            marker="s",
            color=_COLORS["discounted"],
            linestyle="--",
            label="折现回收期",
        )
    ax2 = ax.twinx()
    if "fitness_score_pct" in work.columns and work["fitness_score_pct"].notna().any():
        ax2.plot(
            x,
            work["fitness_score_pct"].to_numpy(dtype=float),
            marker="D",
            color=_COLORS["fitness"],
            linewidth=2.0,
            label="综合适应度",
        )
        best = work[work["objective_best"].astype(bool)]
        if not best.empty:
            bx = float(best.iloc[0]["initial_investment_yuan"]) / 10000.0
            ax2.axvline(bx, color=_COLORS["best"], linestyle="-.", linewidth=1.2, label="适应度最高")
    _apply_style(ax, ylabel="回收期 / 年", xlabel="初始投资 / 万元")
    ax2.set_ylabel("综合适应度 / %")
    ax.set_title("回收期与目标函数随初始投资变化")
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="best")

    path = out_dir / f"{_safe_name(case_name)}_投资变化下经济指标与适应度.svg"
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.96), pad=0.9)
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return [str(path)]
