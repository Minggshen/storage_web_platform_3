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

_SERIES_COLORS = [
    "#1f4e79",
    "#3f7f4c",
    "#b34b4b",
    "#2d8aa0",
    "#c97b2a",
    "#8b5e9a",
    "#5b6770",
    "#9a3f66",
]

_SERIES_MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]

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
    path = path.with_suffix(".svg")
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.97), pad=0.9)
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _history_frame(run_result: LemmingOptimizationRunResult) -> pd.DataFrame:
    hist = pd.DataFrame(run_result.history)
    if hist.empty:
        return hist

    for col in [
        "generation",
        "global_generation",
        "local_generation",
        "local_generations",
        "archive_size",
        "best_npv_yuan",
    ]:
        if col in hist.columns:
            hist[col] = pd.to_numeric(hist[col], errors="coerce")

    if "strategy_id" in hist.columns:
        label = hist["strategy_id"].fillna("").astype(str).str.strip()
        label = label.mask(label.str.lower().isin(["", "nan", "none", "null"]), "整体")
        hist["_strategy_label"] = label
    else:
        hist["_strategy_label"] = "整体"
    sort_col = "generation" if "generation" in hist.columns else None
    if sort_col is not None:
        hist = hist.sort_values(["_strategy_label", sort_col], kind="stable").copy()
    if "local_generation" not in hist.columns or hist["local_generation"].isna().all():
        hist["_display_generation"] = hist.groupby("_strategy_label", sort=False).cumcount() + 1
    else:
        display = hist["local_generation"].copy()
        missing = display.isna()
        if missing.any():
            display.loc[missing] = hist.loc[missing].groupby("_strategy_label", sort=False).cumcount() + 1
        hist["_display_generation"] = display
    return hist


def _plot_history_convergence(ax: plt.Axes, run_result: LemmingOptimizationRunResult) -> None:
    hist = _history_frame(run_result)
    required = {"generation", "best_npv_yuan"}
    if hist.empty or not required.issubset(hist.columns):
        return

    x_col = "_display_generation" if "_display_generation" in hist.columns else "generation"
    hist = hist.dropna(subset=[x_col, "best_npv_yuan"]).copy()
    if hist.empty:
        return

    strategy_labels = [
        label
        for label in hist["_strategy_label"].dropna().astype(str).unique().tolist()
        if label and label != "整体"
    ]
    multi_strategy = len(strategy_labels) > 1
    ax2 = ax.twinx()

    if multi_strategy:
        for idx, (strategy_label, group) in enumerate(hist.groupby("_strategy_label", sort=False)):
            group = group.sort_values(x_col)
            color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
            marker = _SERIES_MARKERS[idx % len(_SERIES_MARKERS)]
            ax.plot(
                group[x_col].to_numpy(dtype=float),
                group["best_npv_yuan"].to_numpy(dtype=float) / 10000.0,
                color=color,
                marker=marker,
                markersize=4.2,
                lw=1.6,
                label=f"{strategy_label} 最优NPV" if len(strategy_labels) <= 8 else "_nolegend_",
            )
            if "archive_size" in group.columns and group["archive_size"].notna().any():
                ax2.plot(
                    group[x_col].to_numpy(dtype=float),
                    group["archive_size"].to_numpy(dtype=float),
                    color=color,
                    linestyle="--",
                    lw=1.25,
                    alpha=0.78,
                    label=f"{strategy_label} Archive" if len(strategy_labels) <= 4 else "_nolegend_",
                )
        _apply_style(ax, ylabel="最优NPV / 万元", xlabel="本型号内部迭代代数")
        ax.set_title("按设备型号分组的收敛历程")
        if len(strategy_labels) > 8:
            ax.text(
                0.02,
                0.92,
                f"共 {len(strategy_labels)} 个设备型号；实线=最优NPV，虚线=Archive大小",
                transform=ax.transAxes,
                fontsize=_LEGEND,
                color=_COLORS["gray"],
                bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#d0d7de", "alpha": 0.86},
            )
    else:
        hist = hist.sort_values(x_col)
        ax.plot(
            hist[x_col].to_numpy(dtype=float),
            hist["best_npv_yuan"].to_numpy(dtype=float) / 10000.0,
            color=_COLORS["base"],
            marker="o",
            lw=1.6,
            label="最优NPV",
        )
        if "archive_size" in hist.columns and hist["archive_size"].notna().any():
            ax2.plot(
                hist[x_col].to_numpy(dtype=float),
                hist["archive_size"].to_numpy(dtype=float),
                color=_COLORS["accent1"],
                marker="s",
                lw=1.6,
                label="Archive大小",
            )
        _apply_style(ax, ylabel="最优NPV / 万元", xlabel="迭代代数")
        ax.set_title("优化收敛历程")

    ax2.set_ylabel("Archive大小")
    ax2.grid(False)
    ax2.spines["top"].set_visible(False)
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    if lines1 or lines2:
        ax.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=_LEGEND, ncol=2 if multi_strategy else 1)


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
        feasible = df[df["feasible"]].copy()
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
        _plot_history_convergence(ax, run_result)
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

        p = out_dir / f"{safe_case}_Pareto与优化过程六面板.svg"
        saved.append(_save(fig, p))

    return saved
