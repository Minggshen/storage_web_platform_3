from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
import textwrap

import numpy as np
import matplotlib.pyplot as plt

from storage_engine_project.visualization.mpl_global import setup_matplotlib_chinese

_COLORS = {
    "base": "#1f4e79",
    "accent1": "#c97b2a",
    "accent2": "#3f7f4c",
    "accent3": "#8b5e9a",
    "accent4": "#b34b4b",
    "gray": "#7f7f7f",
}


def _sanitize_filename(text: str) -> str:
    invalid = '<>:"/\\|?*'
    result = str(text).strip()
    for ch in invalid:
        result = result.replace(ch, "_")
    return result.replace(" ", "_")


def _ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _pretty_title(text: str, suffix: str = "") -> str:
    base = str(text).replace("_", " ")
    if suffix:
        base = f"{base}：{suffix}"
    return "\n".join(textwrap.wrap(base, width=34, break_long_words=False))


def _apply_style(ax: plt.Axes, ylabel: str | None = None) -> None:
    ax.grid(True, linestyle="--", linewidth=0.6, alpha=0.28)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(direction="in")
    if ylabel:
        ax.set_ylabel(ylabel)


def _finalize_and_save(fig: plt.Figure, save_path: Path, rect: tuple[float, float, float, float] = (0.02, 0.02, 0.98, 0.95)) -> str:
    fig.tight_layout(pad=0.9, rect=rect)
    fig.savefig(save_path, dpi=320, bbox_inches="tight")
    plt.close(fig)
    return str(save_path)


def _to_arr(values: Any) -> np.ndarray:
    if values is None:
        return np.asarray([], dtype=float)
    return np.asarray(values, dtype=float).reshape(-1)


def _extract(scale_results: Any) -> dict[str, np.ndarray]:
    points = _read(scale_results, "points", None)
    if points is not None:
        points = list(points)
        if not points:
            return {}
        def g(keys):
            vals=[]
            for p in points:
                v=None
                for k in keys:
                    v=_read(p,k,None)
                    if v is not None:
                        break
                vals.append(np.nan if v is None else float(v))
            return np.asarray(vals,dtype=float)
        data = {
            "scale_factor": g(["scale_factor"]),
            "npv_wan": g(["npv_wan","npv_yuan"]),
            "payback_years": g(["payback_years"]),
            "initial_capex_wan": g(["initial_capex_wan","initial_capex_yuan"]),
            "annual_net_cashflow_wan": g(["annual_net_cashflow_wan","annual_net_cashflow_yuan"]),
            "annual_arbitrage_revenue_wan": g(["annual_arbitrage_revenue_wan","annual_arbitrage_revenue_yuan"]),
            "annual_demand_saving_wan": g(["annual_demand_saving_wan","annual_demand_saving_yuan"]),
            "annual_aux_service_revenue_wan": g(["annual_aux_service_revenue_wan","annual_aux_service_revenue_yuan"]),
            "annual_capacity_revenue_wan": g(["annual_capacity_revenue_wan","annual_capacity_revenue_yuan"]),
            "annual_loss_reduction_revenue_wan": g(["annual_loss_reduction_revenue_wan","annual_loss_reduction_revenue_yuan"]),
            "annual_voltage_penalty_wan": g(["annual_voltage_penalty_wan","annual_voltage_penalty_yuan"]),
            "annual_cycles": g(["annual_cycles","annual_equivalent_cycles"]),
        }
        for k in list(data.keys()):
            if k.endswith("_wan") and np.nanmax(np.abs(data[k])) > 1e4:
                data[k] = data[k] / 10000.0
        return data
    if isinstance(scale_results, Sequence) and not isinstance(scale_results, (str, bytes)) and len(scale_results) > 0:
        return _extract({"points": scale_results})
    x = _to_arr(_read(scale_results, "scale_factor", _read(scale_results, "scale_factors", [])))
    if x.size == 0:
        return {}
    return {
        "scale_factor": x,
        "npv_wan": _to_arr(_read(scale_results, "npv_wan", [])),
        "payback_years": _to_arr(_read(scale_results, "payback_years", [])),
        "initial_capex_wan": _to_arr(_read(scale_results, "initial_capex_wan", [])),
        "annual_net_cashflow_wan": _to_arr(_read(scale_results, "annual_net_cashflow_wan", [])),
        "annual_arbitrage_revenue_wan": _to_arr(_read(scale_results, "annual_arbitrage_revenue_wan", [])),
        "annual_demand_saving_wan": _to_arr(_read(scale_results, "annual_demand_saving_wan", [])),
        "annual_aux_service_revenue_wan": _to_arr(_read(scale_results, "annual_aux_service_revenue_wan", [])),
        "annual_capacity_revenue_wan": _to_arr(_read(scale_results, "annual_capacity_revenue_wan", [])),
        "annual_loss_reduction_revenue_wan": _to_arr(_read(scale_results, "annual_loss_reduction_revenue_wan", [])),
        "annual_voltage_penalty_wan": _to_arr(_read(scale_results, "annual_voltage_penalty_wan", [])),
        "annual_cycles": _to_arr(_read(scale_results, "annual_cycles", [])),
    }


def _best_idx(npv: np.ndarray) -> int:
    valid = np.where(np.isfinite(npv))[0]
    return int(valid[np.argmax(npv[valid])]) if valid.size else 0


def _plot_core(case_name: str, data: dict[str, np.ndarray], output_dir: Path) -> str:
    x = data["scale_factor"]; npv = data["npv_wan"]; pb = data["payback_years"]; capex = data["initial_capex_wan"]
    idx = _best_idx(npv)
    fig, axes = plt.subplots(3, 1, figsize=(7.0, 7.2), sharex=True)
    series = [
        (npv, _COLORS["base"], "o", "NPV / 万元"),
        (pb, _COLORS["accent1"], "s", "回收期 / 年"),
        (capex, _COLORS["accent3"], "^", "初始投资 / 万元"),
    ]
    for i, (ax, (y, c, m, yl)) in enumerate(zip(axes, series)):
        ax.plot(x, y, color=c, marker=m)
        ax.scatter(x[idx], y[idx], s=120, marker="*", color="#c44e52", edgecolors="black", zorder=5)
        _apply_style(ax, yl)
        ax.text(0.01, 0.98, f"({chr(97+i)})", transform=ax.transAxes, va="top", ha="left", fontsize=9, fontweight="bold")
    axes[-1].set_xlabel("规模系数")
    fig.suptitle(_pretty_title(case_name, "规模效应核心指标"), y=0.985, fontsize=11)
    return _finalize_and_save(fig, output_dir / f"{_sanitize_filename(case_name)}_scale_core_metrics.png", rect=(0.02,0.02,0.98,0.95))


def _plot_tradeoff(case_name: str, data: dict[str, np.ndarray], output_dir: Path) -> str:
    x = data["scale_factor"]; npv = data["npv_wan"]; pb = data["payback_years"]; idx = _best_idx(npv)
    fig, ax1 = plt.subplots(figsize=(6.8, 4.4))
    ax1.plot(x, npv, color=_COLORS["base"], marker="o", label="NPV")
    ax1.scatter(x[idx], npv[idx], s=120, marker="*", color="#c44e52", edgecolors="black", zorder=5)
    _apply_style(ax1, "NPV / 万元")
    ax1.set_xlabel("规模系数")
    ax2 = ax1.twinx()
    ax2.plot(x, pb, color=_COLORS["accent1"], marker="s", label="回收期")
    ax2.set_ylabel("回收期 / 年")
    ax2.spines["top"].set_visible(False)
    lines1, labels1 = ax1.get_legend_handles_labels(); lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8)
    ax1.set_title(_pretty_title(case_name, "规模-经济性权衡"), pad=8)
    return _finalize_and_save(fig, output_dir / f"{_sanitize_filename(case_name)}_scale_tradeoff_dual_axis.png")


def _plot_frontier(case_name: str, data: dict[str, np.ndarray], output_dir: Path) -> str:
    x = data["initial_capex_wan"]; y = data["annual_net_cashflow_wan"]
    if y.size == 0 or np.all(~np.isfinite(y)):
        y = data["npv_wan"]
    c = data["scale_factor"]
    idx = _best_idx(data["npv_wan"])
    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    sc = ax.scatter(x, y, c=c, cmap="viridis", s=58, edgecolors="white", linewidths=0.3, alpha=0.82)
    ax.scatter(x[idx], y[idx], s=140, marker="*", color="#c44e52", edgecolors="black", zorder=5, label="最优规模")
    _apply_style(ax, "年净现金流 / 万元")
    ax.set_xlabel("初始投资 / 万元")
    ax.set_title(_pretty_title(case_name, "规模效率前沿"), pad=8)
    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label("规模系数")
    ax.legend(loc="upper left", fontsize=8)
    return _finalize_and_save(fig, output_dir / f"{_sanitize_filename(case_name)}_scale_efficiency_frontier.png")


def _plot_revenue(case_name: str, data: dict[str, np.ndarray], output_dir: Path) -> str | None:
    x = data["scale_factor"]
    items = [
        ("峰谷套利", data.get("annual_arbitrage_revenue_wan", np.array([])), _COLORS["base"], "o"),
        ("需量收益", data.get("annual_demand_saving_wan", np.array([])), _COLORS["accent1"], "s"),
        ("需求响应/VPP", data.get("annual_aux_service_revenue_wan", np.array([])), _COLORS["accent2"], "^"),
        ("容量收益", data.get("annual_capacity_revenue_wan", np.array([])), _COLORS["accent3"], "d"),
        ("网损收益", data.get("annual_loss_reduction_revenue_wan", np.array([])), _COLORS["accent4"], "v"),
    ]
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    has = False
    for label, arr, color, marker in items:
        if arr.size > 0 and np.any(np.isfinite(arr)):
            ax.plot(x, arr, color=color, marker=marker, label=label)
            has = True
    penalty = data.get("annual_voltage_penalty_wan", np.array([]))
    if penalty.size > 0 and np.any(np.isfinite(penalty)):
        ax.plot(x, -penalty, color=_COLORS["gray"], marker="x", label="电压罚金（负向}")
        has = True
    net = data.get("annual_net_cashflow_wan", np.array([]))
    if net.size > 0 and np.any(np.isfinite(net)):
        ax.plot(x, net, color="black", marker="*", linewidth=2.0, label="年净现金流")
        has = True
    if not has:
        plt.close(fig)
        return None
    ax.axhline(0.0, color="black", linewidth=0.8)
    _apply_style(ax, "金额 / 万元")
    ax.set_xlabel("规模系数")
    ax.set_title(_pretty_title(case_name, "收益分项演化"), pad=8)
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.02), fontsize=8)
    return _finalize_and_save(fig, output_dir / f"{_sanitize_filename(case_name)}_scale_revenue_breakdown.png")


def _plot_marginal(case_name: str, data: dict[str, np.ndarray], output_dir: Path) -> str | None:
    x = data["scale_factor"]; capex = data["initial_capex_wan"]; net = data["annual_net_cashflow_wan"]
    if capex.size == 0 or net.size == 0:
        return None
    ratio = np.divide(net, capex, out=np.full_like(net, np.nan), where=np.abs(capex) > 1e-12)
    d_cap = np.diff(capex); d_net = np.diff(net)
    marginal = np.divide(d_net, d_cap, out=np.full_like(d_net, np.nan), where=np.abs(d_cap) > 1e-12)
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 6.0), sharex=True)
    axes[0].plot(x, ratio, color=_COLORS["base"], marker="o")
    _apply_style(axes[0], "年净现金流 / 投资")
    axes[1].plot(x[1:], marginal, color=_COLORS["accent1"], marker="s")
    axes[1].axhline(0.0, color="black", linewidth=0.8)
    _apply_style(axes[1], "Δ净现金流 / Δ投资")
    axes[1].set_xlabel("规模系数")
    axes[0].text(0.01, 0.98, "(a)", transform=axes[0].transAxes, va="top", ha="left", fontsize=9, fontweight="bold")
    axes[1].text(0.01, 0.98, "(b)", transform=axes[1].transAxes, va="top", ha="left", fontsize=9, fontweight="bold")
    fig.suptitle(_pretty_title(case_name, "规模扩展的收益效率变化"), y=0.985, fontsize=11)
    return _finalize_and_save(fig, output_dir / f"{_sanitize_filename(case_name)}_scale_marginal_efficiency.png", rect=(0.02,0.02,0.98,0.95))


def _plot_penalty_cycles(case_name: str, data: dict[str, np.ndarray], output_dir: Path) -> str | None:
    x = data["scale_factor"]; penalty = data.get("annual_voltage_penalty_wan", np.array([])); cycles = data.get("annual_cycles", np.array([]))
    if (penalty.size == 0 or np.all(~np.isfinite(penalty))) and (cycles.size == 0 or np.all(~np.isfinite(cycles))):
        return None
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 6.0), sharex=True)
    if penalty.size > 0 and np.any(np.isfinite(penalty)):
        axes[0].plot(x, penalty, color=_COLORS["accent4"], marker="o")
    _apply_style(axes[0], "电压罚金 / 万元")
    if cycles.size > 0 and np.any(np.isfinite(cycles)):
        axes[1].plot(x, cycles, color=_COLORS["accent2"], marker="s")
    _apply_style(axes[1], "年等效循环次数 / 次")
    axes[1].set_xlabel("规模系数")
    axes[0].text(0.01, 0.98, "(a)", transform=axes[0].transAxes, va="top", ha="left", fontsize=9, fontweight="bold")
    axes[1].text(0.01, 0.98, "(b)", transform=axes[1].transAxes, va="top", ha="left", fontsize=9, fontweight="bold")
    fig.suptitle(_pretty_title(case_name, "电压约束与运行强度"), y=0.985, fontsize=11)
    return _finalize_and_save(fig, output_dir / f"{_sanitize_filename(case_name)}_scale_penalty_cycles.png", rect=(0.02,0.02,0.98,0.95))


def plot_scale_effect(case_name: str, scale_results: Any, output_dir: str | Path = "outputs/paper_figures/scale_effect") -> list[str]:
    setup_matplotlib_chinese()
    output_dir = _ensure_dir(output_dir)
    data = _extract(scale_results)
    if not data:
        return []
    saved = [_plot_core(case_name, data, output_dir), _plot_tradeoff(case_name, data, output_dir), _plot_frontier(case_name, data, output_dir)]
    for fn in (_plot_revenue, _plot_marginal, _plot_penalty_cycles):
        p = fn(case_name, data, output_dir)
        if p:
            saved.append(p)
    return saved
