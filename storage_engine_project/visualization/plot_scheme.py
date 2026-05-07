from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import AutoMinorLocator

from storage_engine_project.optimization.optimization_models import FitnessEvaluationResult
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
    "soft": "#dbe7f3",
}


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


def _finite_float(value: Any, default: float = np.nan) -> float:
    try:
        if value in (None, ""):
            return float(default)
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if np.isfinite(number) else float(default)


def _fmt_value(value: Any, unit: str = "", scale: float = 1.0, digits: int = 2, missing: str = "未计算") -> str:
    number = _finite_float(value)
    if not np.isfinite(number):
        return missing
    return f"{number / scale:.{digits}f}{unit}"


def plot_scheme_overview(case_name: str, best_result: FitnessEvaluationResult, output_dir: str | Path) -> list[str]:
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

    summary = best_result.summary_dict()
    fin = best_result.lifecycle_financial_result
    ann = best_result.annual_operation_result

    fig, axes = plt.subplots(2, 2, figsize=(13.6, 9.8))
    fig.suptitle(f"{case_name}：最优储能设备选型与方案总览", fontsize=_SUPTITLE, fontweight="bold", y=0.992)

    # (a) 文本总览
    ax = axes[0, 0]
    ax.axis("off")
    lines = [
        f"推荐策略：{summary.get('strategy_name', summary.get('strategy_id', ''))}",
        f"策略编号：{summary.get('strategy_id', '')}",
        f"额定功率：{_fmt_value(summary.get('rated_power_kw'), ' kW')}",
        f"额定容量：{_fmt_value(summary.get('rated_energy_kwh'), ' kWh')}",
        f"配置时长：{_fmt_value(summary.get('duration_h'), ' h')}",
        f"初始投资：{_fmt_value(summary.get('initial_investment_yuan'), ' 万元', scale=10000.0)}",
        f"净现值 NPV：{_fmt_value(summary.get('npv_yuan'), ' 万元', scale=10000.0)}",
        f"静态回收期：{_fmt_value(summary.get('simple_payback_years'), ' 年')}",
        f"IRR：{_fmt_value(_finite_float(summary.get('irr')) * 100.0, ' %')}",
        f"年净经营现金流：{_fmt_value(summary.get('annual_net_operating_cashflow_yuan'), ' 万元', scale=10000.0)}",
        f"年等效循环：{_fmt_value(summary.get('annual_equivalent_full_cycles'), ' 次')}",
    ]
    text = "\n".join(lines)
    ax.text(0.03, 0.95, text, va="top", ha="left", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#cccccc", alpha=0.95))
    ax.set_title("设备选型与关键指标")
    _panel(ax, "a")

    # (b) 规模与运行强度
    ax = axes[0, 1]
    duration_h = _finite_float(summary.get("duration_h"))
    vals = np.array([
        _finite_float(summary.get("rated_power_kw")) / 1000.0,
        _finite_float(summary.get("rated_energy_kwh")) / 1000.0,
        duration_h,
        _finite_float(summary.get("annual_equivalent_full_cycles")),
    ], dtype=float)
    labels = ["功率\n(MW)", "容量\n(MWh)", "时长\n(h)", "年循环\n(次)"]
    ax.bar(labels, vals, color=[_COLORS["base"], _COLORS["accent1"], _COLORS["accent2"], _COLORS["accent3"]])
    _apply_style(ax, ylabel="指标值")
    ax.set_title("配置规模与运行强度")
    _panel(ax, "b")

    # (c) 初始投资构成
    ax = axes[1, 0]
    if fin is not None:
        cap = fin.capital_cost_breakdown
        vals = np.array([
            cap.energy_capex_yuan,
            cap.power_capex_yuan,
            cap.safety_markup_yuan,
            cap.integration_markup_yuan,
            cap.other_capex_yuan,
        ], dtype=float) / 10000.0
        labels = ["容量侧", "功率侧", "安全附加", "集成附加", "其他"]
        ax.pie(vals, labels=labels, autopct="%.1f%%", startangle=90,
               colors=[_COLORS["base"], _COLORS["accent1"], _COLORS["accent4"], _COLORS["accent2"], _COLORS["gray"]],
               textprops={"fontsize": 9})
    ax.set_title("初始投资构成")
    _panel(ax, "c")

    # (d) 年度价值构成
    ax = axes[1, 1]
    if fin is not None:
        audit = fin.annual_revenue_audit
        items = [
            ("套利收益", audit.annual_arbitrage_revenue_yuan / 10000.0),
            ("需量收益", audit.annual_demand_saving_yuan / 10000.0),
            ("服务净收益", audit.annual_service_net_revenue_yuan / 10000.0),
            ("退化成本", -audit.annual_degradation_cost_yuan / 10000.0),
            ("运维成本", -audit.annual_om_cost_yuan / 10000.0),
            ("网侧罚金", -(audit.annual_transformer_penalty_yuan + audit.annual_voltage_penalty_yuan) / 10000.0),
        ]
        ys = np.arange(len(items))[::-1]
        vals = np.array([v for _, v in items], dtype=float)
        cols = [_COLORS["base"] if v >= 0 else _COLORS["accent4"] for v in vals]
        ax.barh(ys, vals, color=cols, alpha=0.88)
        ax.set_yticks(ys)
        ax.set_yticklabels([k for k, _ in items])
        ax.axvline(0.0, color="black", lw=0.7)
        _apply_style(ax, xlabel="金额 / 万元")
    ax.set_title("年度价值贡献")
    _panel(ax, "d")

    p = out_dir / f"{safe_case}_设备选型与方案总览.png"
    saved.append(_save(fig, p))

    # 摘要表
    summary_df = pd.DataFrame([summary])
    p_csv = out_dir / f"{safe_case}_设备选型摘要表.csv"
    summary_df.to_csv(p_csv, index=False, encoding="utf-8-sig")
    saved.append(str(p_csv))

    return saved
