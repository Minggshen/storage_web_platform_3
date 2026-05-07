from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationResult
from storage_engine_project.visualization.mpl_global import setup_matplotlib_chinese


_SUPTITLE = 16
_TITLE = 12
_LABEL = 11
_TICK = 9
_LEGEND = 9
_LW = 2.0

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


def _daily_throughput(ann: AnnualOperationResult) -> np.ndarray:
    return np.sum(ann.exec_charge_kw + ann.exec_discharge_kw + ann.exec_service_kw, axis=1)


def _daily_cashflow(ann: AnnualOperationResult) -> np.ndarray:
    return np.sum(
        ann.arbitrage_revenue_yuan
        + ann.service_capacity_revenue_yuan
        + ann.service_delivery_revenue_yuan
        - ann.service_penalty_yuan
        - ann.degradation_cost_yuan
        - ann.transformer_penalty_yuan
        - ann.voltage_penalty_yuan,
        axis=1,
    )


def _moving_average(x: np.ndarray, window: int = 7) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size == 0 or window <= 1:
        return x.copy()
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(x, kernel, mode="same")


def _representative_day(ann: AnnualOperationResult) -> int:
    groups = ann.metadata.get("represented_day_groups", None)
    if groups:
        max_group = max(len(g[1]) for g in groups)
        if max_group > 1:
            best = max(groups, key=lambda x: len(x[1]))
            return int(best[0])

    daily_throughput = _daily_throughput(ann)
    daily_cf = _daily_cashflow(ann)
    thr_rank = (daily_throughput - np.nanmin(daily_throughput)) / max(np.nanmax(daily_throughput) - np.nanmin(daily_throughput), 1e-9)
    med_cf = float(np.nanmedian(daily_cf))
    cf_closeness = 1.0 - np.abs(daily_cf - med_cf) / max(np.nanmax(np.abs(daily_cf - med_cf)), 1e-9)
    score = 0.65 * thr_rank + 0.35 * cf_closeness
    return int(np.nanargmax(score))


def _representative_day_summary(ann: AnnualOperationResult, day: int) -> dict[str, float]:
    return {
        "代表日序号": float(day + 1),
        "代表日净经营现金流_元": float(np.sum(
            ann.arbitrage_revenue_yuan[day]
            + ann.service_capacity_revenue_yuan[day]
            + ann.service_delivery_revenue_yuan[day]
            - ann.service_penalty_yuan[day]
            - ann.degradation_cost_yuan[day]
            - ann.transformer_penalty_yuan[day]
            - ann.voltage_penalty_yuan[day]
        )),
        "代表日吞吐量_kWh": float(np.sum(ann.exec_charge_kw[day] + ann.exec_discharge_kw[day] + ann.exec_service_kw[day])),
        "代表日最大充电功率_kW": float(np.max(ann.exec_charge_kw[day])),
        "代表日最大放电功率_kW": float(np.max(ann.exec_discharge_kw[day])),
        "代表日SOC起点": float(ann.soc_hourly_path[day, 0]),
        "代表日SOC终点": float(ann.soc_hourly_path[day, -1]),
    }


def plot_dispatch_profiles(case_name: str, annual_result: AnnualOperationResult, output_dir: str | Path) -> list[str]:
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
    rep_day = _representative_day(annual_result)
    hours = np.arange(24)
    days = np.arange(1, 366)

    monthly = annual_result.monthly_summary_dataframe()
    daily_throughput = _daily_throughput(annual_result)
    daily_cf = _daily_cashflow(annual_result)

    fig, axes = plt.subplots(3, 2, figsize=(15.5, 12.5))
    fig.suptitle(f"{case_name}：储能运行过程与运行特征总览", fontsize=_SUPTITLE, fontweight="bold", y=0.995)

    ax = axes[0, 0]
    net_load = annual_result.actual_net_load_kw[rep_day]
    ax.plot(hours, net_load, color=_COLORS["base"], lw=_LW, marker="o", label="用户净负荷")
    ax2 = ax.twinx()
    ax2.step(hours, annual_result.tariff_yuan_per_kwh[rep_day], where="post", color=_COLORS["accent3"], lw=1.6, label="分时电价")
    _apply_style(ax, ylabel="净负荷 / kW")
    ax.set_title(f"代表日负荷与电价（第{rep_day + 1}天）")
    ax.set_xticks(np.arange(0, 24, 2))
    ax2.set_ylabel("电价 / 元·kWh$^{-1}$")
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
    _panel(ax, "a")

    ax = axes[0, 1]
    ax.plot(hours, annual_result.grid_exchange_kw[rep_day], color="black", lw=1.6, ls="--", label="并网交换功率")
    ax.bar(hours, annual_result.exec_discharge_kw[rep_day], color=_COLORS["accent2"], alpha=0.85, label="放电功率")
    ax.bar(hours, -annual_result.exec_charge_kw[rep_day], color=_COLORS["accent1"], alpha=0.85, label="充电功率")
    ax.axhline(0.0, color="black", lw=0.7)
    _apply_style(ax, ylabel="功率 / kW")
    ax.set_title("代表日充放电与并网功率")
    ax.set_xticks(np.arange(0, 24, 2))
    ax.legend(loc="upper right", ncol=3)
    _panel(ax, "b")

    ax = axes[1, 0]
    soc = annual_result.soc_hourly_path[rep_day]
    hourly_cf = (
        annual_result.arbitrage_revenue_yuan[rep_day]
        + annual_result.service_capacity_revenue_yuan[rep_day]
        + annual_result.service_delivery_revenue_yuan[rep_day]
        - annual_result.service_penalty_yuan[rep_day]
        - annual_result.degradation_cost_yuan[rep_day]
        - annual_result.transformer_penalty_yuan[rep_day]
        - annual_result.voltage_penalty_yuan[rep_day]
    )
    ax.step(np.arange(25), soc, where="post", color=_COLORS["accent2"], lw=_LW, label="SOC轨迹")
    ax.fill_between(np.arange(25), soc, 0.0, step="post", color="#dfeadf", alpha=0.55)
    ax2 = ax.twinx()
    ax2.bar(hours, hourly_cf, color=_COLORS["accent4"], alpha=0.25, label="小时净收益")
    _apply_style(ax, ylabel="SOC / p.u.")
    ax.set_title("代表日SOC与小时净收益")
    ax.set_xticks(np.arange(0, 24, 2))
    ax2.set_ylabel("净收益 / 元")
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right")
    _panel(ax, "c")

    ax = axes[1, 1]
    m = monthly["month"].to_numpy(dtype=int)
    arb = monthly["arbitrage_revenue_yuan"].to_numpy(dtype=float) / 10000.0
    dem = monthly["demand_saving_yuan"].to_numpy(dtype=float) / 10000.0
    cost = (
        monthly["degradation_cost_yuan"].to_numpy(dtype=float)
        + monthly["transformer_penalty_yuan"].to_numpy(dtype=float)
        + monthly["voltage_penalty_yuan"].to_numpy(dtype=float)
    ) / 10000.0
    net = monthly["net_operating_cashflow_yuan"].to_numpy(dtype=float) / 10000.0
    ax.bar(m, arb, color=_COLORS["base"], label="套利收益")
    ax.bar(m, dem, bottom=arb, color=_COLORS["accent1"], label="需量收益")
    ax.bar(m, -cost, color=_COLORS["accent4"], label="退化与罚金")
    ax.plot(m, net, color="black", marker="o", lw=1.6, label="月净经营现金流")
    ax.axhline(0.0, color="black", lw=0.7)
    _apply_style(ax, ylabel="金额 / 万元")
    ax.set_title("月度收益与成本分解")
    ax.set_xticks(m)
    ax.legend(loc="upper center", ncol=4)
    _panel(ax, "d")

    ax = axes[2, 0]
    ax.plot(days, daily_throughput, color=_COLORS["base"], alpha=0.35, lw=1.1, label="日吞吐量")
    ax.plot(days, _moving_average(daily_throughput, 7), color=_COLORS["accent1"], lw=1.8, label="7日滑动均值")
    _apply_style(ax, ylabel="吞吐量 / kWh", xlabel="日期序号")
    ax.set_title("全年运行强度变化")
    ax.legend(loc="upper right")
    _panel(ax, "e")

    ax = axes[2, 1]
    ax.plot(days, daily_cf, color=_COLORS["accent4"], alpha=0.35, lw=1.0, label="日净经营现金流")
    ax.plot(days, _moving_average(daily_cf, 7), color="black", lw=1.8, label="7日滑动均值")
    _apply_style(ax, ylabel="净经营现金流 / 元", xlabel="日期序号")
    ax.set_title("全年经营收益波动")
    ax.legend(loc="upper right")
    _panel(ax, "f")

    p = out_dir / f"{safe_case}_运行总览六联图.png"
    saved.append(_save(fig, p))

    fig, axes = plt.subplots(4, 1, figsize=(12.0, 11.2), sharex=True)
    fig.suptitle(f"{case_name}：代表性日详细运行图（第{rep_day + 1}天）", fontsize=_SUPTITLE, fontweight="bold", y=0.995)

    axes[0].step(hours, annual_result.tariff_yuan_per_kwh[rep_day], where="post", color=_COLORS["accent3"], lw=_LW)
    _apply_style(axes[0], ylabel="电价 / 元·kWh$^{-1}$")
    axes[0].set_title("分时电价")
    _panel(axes[0], "a")

    axes[1].plot(hours, annual_result.actual_net_load_kw[rep_day], color=_COLORS["gray"], lw=1.6, label="用户净负荷")
    axes[1].plot(hours, annual_result.grid_exchange_kw[rep_day], color=_COLORS["base"], lw=2.0, label="并网交换功率")
    _apply_style(axes[1], ylabel="功率 / kW")
    axes[1].set_title("用户负荷与并网功率")
    axes[1].legend(loc="upper right")
    _panel(axes[1], "b")

    axes[2].bar(hours, annual_result.exec_discharge_kw[rep_day], color=_COLORS["accent2"], alpha=0.85, label="放电")
    axes[2].bar(hours, -annual_result.exec_charge_kw[rep_day], color=_COLORS["accent1"], alpha=0.85, label="充电")
    axes[2].axhline(0.0, color="black", lw=0.7)
    _apply_style(axes[2], ylabel="功率 / kW")
    axes[2].set_title("储能充放电功率")
    axes[2].legend(loc="upper right", ncol=2)
    _panel(axes[2], "c")

    axes[3].step(np.arange(25), annual_result.soc_hourly_path[rep_day], where="post", color=_COLORS["accent2"], lw=_LW)
    _apply_style(axes[3], ylabel="SOC / p.u.", xlabel="时刻 / h")
    axes[3].set_title("储能荷电状态轨迹")
    axes[3].set_xticks(np.arange(0, 25, 2))
    _panel(axes[3], "d")

    p = out_dir / f"{safe_case}_代表日详细运行图.png"
    saved.append(_save(fig, p))

    rep_df = pd.DataFrame(
        {
            "hour": np.arange(24),
            "tariff_yuan_per_kwh": annual_result.tariff_yuan_per_kwh[rep_day],
            "actual_net_load_kw": annual_result.actual_net_load_kw[rep_day],
            "grid_exchange_kw": annual_result.grid_exchange_kw[rep_day],
            "exec_charge_kw": annual_result.exec_charge_kw[rep_day],
            "exec_discharge_kw": annual_result.exec_discharge_kw[rep_day],
            "soc_open": annual_result.soc_hourly_path[rep_day, :-1],
            "soc_close": annual_result.soc_hourly_path[rep_day, 1:],
        }
    )
    p_csv = out_dir / f"{safe_case}_代表日运行数据表.csv"
    rep_df.to_csv(p_csv, index=False, encoding="utf-8-sig")
    saved.append(str(p_csv))

    daily_df = pd.DataFrame(
        {
            "day_index": days,
            "daily_throughput_kwh": daily_throughput,
            "daily_net_cashflow_yuan": daily_cf,
            "soc_open": annual_result.soc_daily_open,
            "soc_close": annual_result.soc_daily_close,
        }
    )
    p_csv = out_dir / f"{safe_case}_年度日尺度运行表.csv"
    daily_df.to_csv(p_csv, index=False, encoding="utf-8-sig")
    saved.append(str(p_csv))

    p_csv = out_dir / f"{safe_case}_代表日摘要.csv"
    pd.DataFrame([_representative_day_summary(annual_result, rep_day)]).to_csv(p_csv, index=False, encoding="utf-8-sig")
    saved.append(str(p_csv))

    return saved
