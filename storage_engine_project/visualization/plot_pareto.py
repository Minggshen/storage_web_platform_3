from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import AutoMinorLocator

from storage_engine_project.optimization.lemming_optimizer import LemmingOptimizationRunResult
from storage_engine_project.visualization.mpl_global import setup_matplotlib_chinese

_TITLE = 12
_SUPTITLE = 14
_LABEL = 10.5
_TICK = 9
_LEGEND = 8.5

_COLORS = {
    "base": "#1f4e79",
    "accent1": "#c97b2a",
    "accent2": "#3f7f4c",
    "accent3": "#8b5e9a",
    "accent4": "#b34b4b",
    "gray": "#7f7f7f",
}

_PARETO_NUMERIC_COLUMNS = [
    "initial_investment_yuan",
    "npv_yuan",
    "simple_payback_years",
    "duration_h",
    "rated_power_kw",
    "rated_energy_kwh",
    "annual_equivalent_full_cycles",
]


def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_name(name: str) -> str:
    invalid = '<>:"/\\|?*'
    out = str(name).strip()
    for ch in invalid:
        out = out.replace(ch, '_')
    return out.replace(' ', '_')


def _apply_style(ax: plt.Axes, ylabel: str | None = None, xlabel: str | None = None) -> None:
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.22)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="in")
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)


def _panel(ax: plt.Axes, tag: str) -> None:
    ax.text(0.01, 0.98, f"({tag})", transform=ax.transAxes, va="top", ha="left", fontsize=9, fontweight="bold")


def _save(fig: plt.Figure, path: Path) -> str:
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.97), pad=0.9)
    fig.savefig(path, dpi=320, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _records(run_result: LemmingOptimizationRunResult) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for r in run_result.archive_results:
        row = r.summary_dict()
        row["feasible"] = bool(r.feasible)
        row["total_violation"] = float(r.constraint_vector.total_violation())
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def plot_pareto_front(case_name: str, run_result: LemmingOptimizationRunResult, output_dir: str | Path) -> list[str]:
    setup_matplotlib_chinese()
    plt.rcParams.update({
        "font.size": _TICK,
        "axes.titlesize": _TITLE,
        "axes.labelsize": _LABEL,
        "xtick.labelsize": _TICK,
        "ytick.labelsize": _TICK,
        "legend.fontsize": _LEGEND,
    })

    out_dir = _ensure_dir(output_dir)
    saved: list[str] = []
    safe_case = _safe_name(case_name)

    df = _records(run_result)
    if not df.empty:
        feasible = df[df["feasible"] == True].copy()
        if feasible.empty:
            feasible = df.copy()

        p_csv = out_dir / f"{safe_case}_Archive解集明细表.csv"
        feasible.to_csv(p_csv, index=False, encoding="utf-8-sig")
        saved.append(str(p_csv))

        missing = [col for col in _PARETO_NUMERIC_COLUMNS if col not in feasible.columns]
        if missing:
            return saved

        plot_df = feasible.copy()
        for col in _PARETO_NUMERIC_COLUMNS:
            plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")
        plot_df = plot_df.dropna(
            subset=[
                "initial_investment_yuan",
                "npv_yuan",
                "duration_h",
                "rated_power_kw",
                "rated_energy_kwh",
                "annual_equivalent_full_cycles",
            ]
        )
        if plot_df.empty:
            return saved

        fig, axes = plt.subplots(2, 2, figsize=(13.8, 10.4))
        fig.suptitle(f"{case_name}：优化过程与Pareto解集特征", fontsize=_SUPTITLE, fontweight="bold", y=0.992)

        # (a) NPV-投资散点
        ax = axes[0, 0]
        x = plot_df["initial_investment_yuan"].to_numpy(dtype=float) / 10000.0
        y = plot_df["npv_yuan"].to_numpy(dtype=float) / 10000.0
        c = plot_df["simple_payback_years"].fillna(99.0).to_numpy(dtype=float)
        sc = ax.scatter(x, y, c=c, s=54, alpha=0.85, cmap="viridis", edgecolors="white", linewidths=0.3)
        _apply_style(ax, ylabel="净现值 NPV / 万元", xlabel="初始投资 / 万元")
        ax.set_title("Archive解集经济性散点图")
        cb = fig.colorbar(sc, ax=ax, pad=0.02)
        cb.set_label("静态回收期 / 年")
        if run_result.best_result is not None:
            best = run_result.best_result.summary_dict()
            bx = float(best.get("initial_investment_yuan", np.nan)) / 10000.0
            by = float(best.get("npv_yuan", np.nan)) / 10000.0
            if np.isfinite(bx) and np.isfinite(by):
                ax.scatter([bx], [by], marker="*", s=220, color=_COLORS["accent4"], edgecolors="black", linewidths=0.8)
                ax.annotate("最终折中解", (bx, by), textcoords="offset points", xytext=(8, 6))
        _panel(ax, "a")

        # (b) 功率-时长-策略分布
        ax = axes[0, 1]
        duration = plot_df["duration_h"].to_numpy(dtype=float)
        power = plot_df["rated_power_kw"].to_numpy(dtype=float) / 1000.0
        size = np.clip(plot_df["rated_energy_kwh"].to_numpy(dtype=float) / 50.0, 36, 180)
        sc = ax.scatter(power, duration, s=size, c=plot_df["npv_yuan"].to_numpy(dtype=float) / 10000.0, cmap="plasma", alpha=0.85, edgecolors="white", linewidths=0.3)
        _apply_style(ax, ylabel="配置时长 / h", xlabel="额定功率 / MW")
        ax.set_title("配置规模与解集分布")
        cb = fig.colorbar(sc, ax=ax, pad=0.02)
        cb.set_label("NPV / 万元")
        _panel(ax, "b")

        # (c) 优化收敛
        ax = axes[1, 0]
        hist = pd.DataFrame(run_result.history)
        if not hist.empty:
            gen = hist["generation"].to_numpy(dtype=float)
            ax.plot(gen, hist["best_npv_yuan"].to_numpy(dtype=float) / 10000.0, color=_COLORS["base"], marker="o", lw=1.6, label="最优NPV")
            ax2 = ax.twinx()
            ax2.plot(gen, hist["archive_size"].to_numpy(dtype=float), color=_COLORS["accent1"], marker="s", lw=1.6, label="Archive大小")
            _apply_style(ax, ylabel="最优NPV / 万元", xlabel="迭代代数")
            ax2.set_ylabel("Archive大小")
            ax.set_title("优化收敛历程")
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc="lower right")
        _panel(ax, "c")

        # (d) 安全与运行强度
        ax = axes[1, 1]
        cyc = plot_df["annual_equivalent_full_cycles"].to_numpy(dtype=float)
        pb = plot_df["simple_payback_years"].fillna(99.0).to_numpy(dtype=float)
        sc = ax.scatter(cyc, pb, c=plot_df["npv_yuan"].to_numpy(dtype=float) / 10000.0, s=56, cmap="coolwarm", alpha=0.85, edgecolors="white", linewidths=0.3)
        _apply_style(ax, ylabel="静态回收期 / 年", xlabel="年等效循环次数 / 次")
        ax.set_title("运行强度与经济性关系")
        cb = fig.colorbar(sc, ax=ax, pad=0.02)
        cb.set_label("NPV / 万元")
        _panel(ax, "d")

        p = out_dir / f"{safe_case}_Pareto与优化过程六面板.png"
        saved.append(_save(fig, p))

    return saved
