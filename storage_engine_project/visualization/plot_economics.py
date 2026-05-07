from __future__ import annotations

from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from storage_engine_project.economics.economic_result_models import LifecycleFinancialResult
from storage_engine_project.visualization.mpl_global import setup_matplotlib_chinese

_SUPTITLE = 16
_TITLE = 12
_LABEL = 11
_TICK = 9
_LEGEND = 9

_COLORS = {
    "base": "#1f4e79",
    "accent1": "#d08a33",
    "accent2": "#4f8f5b",
    "accent3": "#8e63a9",
    "accent4": "#c67a7a",
    "gray": "#8a8a8a",
}


def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_name(text: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "_", str(text))


def _apply_style(ax: plt.Axes, ylabel: str | None = None, xlabel: str | None = None) -> None:
    ax.grid(True, linestyle="--", alpha=0.25)
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _panel(ax: plt.Axes, tag: str) -> None:
    ax.text(0.01, 0.98, f"({tag})", transform=ax.transAxes, va="top", ha="left", fontsize=9, fontweight="bold")


def _save(fig: plt.Figure, path: Path) -> str:
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.97), pad=0.9)
    fig.savefig(path, dpi=320, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def _safe_float(x: float | None) -> float:
    return float(x) if x is not None else float("nan")


def plot_financial_diagnostics(case_name: str, financial_result: LifecycleFinancialResult, output_dir: str | Path) -> list[str]:
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

    cap = financial_result.capital_cost_breakdown
    audit = financial_result.annual_revenue_audit
    cash_df = financial_result.cashflow_dataframe().copy()

    years = cash_df["year"].to_numpy(dtype=float)
    net = cash_df["net_cashflow_yuan"].to_numpy(dtype=float) / 10000.0
    disc = cash_df["discounted_net_cashflow_yuan"].to_numpy(dtype=float) / 10000.0
    cumulative_discounted = -financial_result.initial_investment_yuan / 10000.0 + np.cumsum(disc)

    fig, axes = plt.subplots(3, 2, figsize=(15.5, 12.5))
    fig.suptitle(f"{case_name}：储能经济性分析总览", fontsize=_SUPTITLE, fontweight="bold", y=0.995)

    ax = axes[0, 0]
    labels = ["容量侧", "功率侧", "安全附加", "集成附加", "其他"]
    vals = np.array([
        cap.energy_capex_yuan,
        cap.power_capex_yuan,
        cap.safety_markup_yuan,
        cap.integration_markup_yuan,
        cap.other_capex_yuan,
    ], dtype=float) / 10000.0
    ax.bar(labels, vals, color=[_COLORS["base"], _COLORS["accent1"], _COLORS["accent4"], _COLORS["accent2"], _COLORS["gray"]])
    _apply_style(ax, ylabel="金额 / 万元")
    ax.set_title("初始投资构成")
    _panel(ax, "a")

    ax = axes[0, 1]
    items = [
        ("套利收益", audit.annual_arbitrage_revenue_yuan / 10000.0),
        ("需量收益", audit.annual_demand_saving_yuan / 10000.0),
        ("服务净收益", audit.annual_service_net_revenue_yuan / 10000.0),
        ("退化成本", -audit.annual_degradation_cost_yuan / 10000.0),
        ("运维成本", -audit.annual_om_cost_yuan / 10000.0),
        ("网侧罚金", -(audit.annual_transformer_penalty_yuan + audit.annual_voltage_penalty_yuan) / 10000.0),
    ]
    y = np.arange(len(items))
    vals = [x[1] for x in items]
    ax.barh(y, vals, color=[_COLORS["base"] if v >= 0 else _COLORS["accent4"] for v in vals])
    ax.axvline(0.0, color="black", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([x[0] for x in items])
    _apply_style(ax, xlabel="金额 / 万元")
    ax.set_title("年度收益与成本分解")
    _panel(ax, "b")

    ax = axes[1, 0]
    ax.bar(years, net, color="#d8e4ef", edgecolor="#7ea3c7", label="年度净现金流")
    ax.plot(years, disc, color=_COLORS["accent1"], marker="o", lw=1.5, label="折现净现金流")
    _apply_style(ax, ylabel="金额 / 万元")
    ax.set_title("全寿命期年度现金流")
    ax.legend(loc="upper right")
    _panel(ax, "c")

    ax = axes[1, 1]
    ax.plot(years, cumulative_discounted, color=_COLORS["base"], marker="o", lw=1.6, label="累计折现现金流")
    ax.axhline(0.0, color="black", lw=0.8)
    dpb = _safe_float(financial_result.discounted_payback_years)
    if np.isfinite(dpb):
        ax.axvline(dpb, color=_COLORS["accent4"], ls="--", lw=1.2, label=f"折现回收期 {dpb:.2f} 年")
    _apply_style(ax, ylabel="累计折现现金流 / 万元")
    ax.set_title("累计折现现金流与折现回收期")
    ax.legend(loc="lower right")
    _panel(ax, "d")

    ax = axes[2, 0]
    metric_labels = ["NPV\n(万元)", "IRR\n(%)", "静态回收期\n(年)", "折现回收期\n(年)", "年均净现金流\n(万元)"]
    metric_vals = [
        financial_result.npv_yuan / 10000.0,
        (_safe_float(financial_result.irr) * 100.0) if np.isfinite(_safe_float(financial_result.irr)) else np.nan,
        _safe_float(financial_result.simple_payback_years),
        _safe_float(financial_result.discounted_payback_years),
        financial_result.annualized_net_cashflow_yuan / 10000.0,
    ]
    ax.bar(metric_labels, metric_vals, color=[_COLORS["base"], _COLORS["accent2"], _COLORS["accent1"], _COLORS["accent3"], _COLORS["gray"]])
    _apply_style(ax, ylabel="指标值")
    ax.set_title("关键财务指标")
    _panel(ax, "e")

    ax = axes[2, 1]
    run_labels = ["额定功率\n(MW)", "额定容量\n(MWh)", "时长\n(h)", "年等效循环\n(次)", "年吞吐量\n(MWh)"]
    run_vals = [
        financial_result.rated_power_kw / 1000.0,
        financial_result.rated_energy_kwh / 1000.0,
        financial_result.rated_energy_kwh / max(financial_result.rated_power_kw, 1e-9),
        audit.annual_equivalent_full_cycles,
        audit.annual_battery_throughput_kwh / 1000.0,
    ]
    ax.bar(run_labels, run_vals, color=[_COLORS["base"], _COLORS["accent1"], _COLORS["accent2"], _COLORS["accent3"], _COLORS["gray"]])
    _apply_style(ax, ylabel="数值")
    ax.set_title("设备规模与运行强度")
    _panel(ax, "f")

    p = out_dir / f"{safe_case}_经济性分析六联图.png"
    saved.append(_save(fig, p))

    if hasattr(financial_result, "summary_dict"):
        pd.DataFrame([financial_result.summary_dict()]).to_csv(
            out_dir / f"{safe_case}_财务诊断摘要表.csv", index=False, encoding="utf-8-sig"
        )
        saved.append(str(out_dir / f"{safe_case}_财务诊断摘要表.csv"))

    return saved
