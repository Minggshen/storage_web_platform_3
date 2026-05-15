from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
import csv
import numpy as np
import matplotlib.pyplot as plt
import textwrap

from storage_engine_project.logging_config import get_logger
from storage_engine_project.visualization.mpl_global import setup_matplotlib_chinese

logger = get_logger(__name__)


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _pretty_title(text: str, suffix: str = "") -> str:
    base = str(text).replace("_", " ")
    if suffix:
        base = f"{base}：{suffix}"
    return "\n".join(textwrap.wrap(base, width=34, break_long_words=False))


def _ordered_fieldnames(summary_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for row in summary_rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                keys.append(str(key))
    return keys


def print_summary_table(summary_rows: Sequence[Mapping[str, Any]]) -> None:
    if not summary_rows:
        logger.info("未生成任何汇总结果。")
        return
    logger.info("=" * 180)
    logger.info("{:^180}".format("分布式储能配置汇总表（常用设备方案 / 高安全设备方案）"))
    logger.info("=" * 180)
    header = (
        f"{'场景名称':<20} | {'方案':<12} | {'节点':>4} | {'功率(kW)':>12} | {'容量(kWh)':>12} | "
        f"{'时长(h)':>8} | {'NPV(万元)':>11} | {'回收期(年)':>12} | {'IRR(%)':>9} | {'安全分':>8} | {'投资(万元)':>12}"
    )
    logger.info(header)
    logger.info("-" * 180)
    for row in summary_rows:
        logger.info(
            "%s | %s | %4d | %12.2f | %12.2f | %8.2f | %11.2f | %12.2f | %9.2f | %8.3f | %12.2f",
            str(row.get('scenario', '未命名场景'))[:20],
            str(row.get('scheme_label', 'standard'))[:12],
            int(_safe_float(row.get('node', 0))),
            _safe_float(row.get('power_kw', 0.0)),
            _safe_float(row.get('energy_kwh', 0.0)),
            _safe_float(row.get('duration_h', 0.0)),
            _safe_float(row.get('npv_wan', 0.0)),
            _safe_float(row.get('payback_years', 0.0)),
            _safe_float(row.get('irr_percent', 0.0)),
            _safe_float(row.get('safety_score', 0.0)),
            _safe_float(row.get('initial_capex_yuan', 0.0)) / 10000.0,
        )
    logger.info("=" * 180)


def save_summary_csv(summary_rows: Sequence[Mapping[str, Any]], output_dir: str | Path = "outputs/reports", file_name: str = "summary_table.csv") -> str | None:
    if not summary_rows:
        return None
    output_dir = _ensure_dir(output_dir)
    save_path = output_dir / _sanitize_filename(file_name)
    fieldnames = _ordered_fieldnames(summary_rows)
    with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in summary_rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    return str(save_path)


def _build_scheme_delta_row(scenario_name: str, common_row: Mapping[str, Any], safe_row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scenario": scenario_name,
        "common_power_kw": _safe_float(common_row.get("power_kw", 0.0)),
        "common_energy_kwh": _safe_float(common_row.get("energy_kwh", 0.0)),
        "safe_power_kw": _safe_float(safe_row.get("power_kw", 0.0)),
        "safe_energy_kwh": _safe_float(safe_row.get("energy_kwh", 0.0)),
        "delta_initial_capex_yuan": _safe_float(safe_row.get("initial_capex_yuan", 0.0)) - _safe_float(common_row.get("initial_capex_yuan", 0.0)),
        "delta_npv_wan": _safe_float(safe_row.get("npv_wan", 0.0)) - _safe_float(common_row.get("npv_wan", 0.0)),
        "delta_payback_years": _safe_float(safe_row.get("payback_years", 0.0)) - _safe_float(common_row.get("payback_years", 0.0)),
        "delta_irr_percent": _safe_float(safe_row.get("irr_percent", 0.0)) - _safe_float(common_row.get("irr_percent", 0.0)),
        "delta_annual_net_cashflow_yuan": _safe_float(safe_row.get("annual_net_cashflow_after_replacement_equivalent_yuan", safe_row.get("annual_net_cashflow_yuan", 0.0))) - _safe_float(common_row.get("annual_net_cashflow_after_replacement_equivalent_yuan", common_row.get("annual_net_cashflow_yuan", 0.0))),
        "delta_safety_score": _safe_float(safe_row.get("safety_score", 0.0)) - _safe_float(common_row.get("safety_score", 0.0)),
    }


def _save_scheme_delta_csv(scenario_name: str, common_row: Mapping[str, Any], safe_row: Mapping[str, Any], output_dir: Path) -> str:
    save_path = output_dir / f"{_sanitize_filename(scenario_name)}_common_vs_high_safety_delta.csv"
    row = _build_scheme_delta_row(scenario_name, common_row, safe_row)
    with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader(); writer.writerow(row)
    return str(save_path)


def _save_scheme_delta_plot(scenario_name: str, common_row: Mapping[str, Any], safe_row: Mapping[str, Any], output_dir: Path) -> str:
    setup_matplotlib_chinese()
    metrics = {
        "增量投资\n(万元)": (_safe_float(safe_row.get("initial_capex_yuan", 0.0)) - _safe_float(common_row.get("initial_capex_yuan", 0.0))) / 10000.0,
        "增量年净现金流\n(万元)": (_safe_float(safe_row.get("annual_net_cashflow_after_replacement_equivalent_yuan", safe_row.get("annual_net_cashflow_yuan", 0.0))) - _safe_float(common_row.get("annual_net_cashflow_after_replacement_equivalent_yuan", common_row.get("annual_net_cashflow_yuan", 0.0)))) / 10000.0,
        "增量NPV\n(万元)": _safe_float(safe_row.get("npv_wan", 0.0)) - _safe_float(common_row.get("npv_wan", 0.0)),
        "回收期变化\n(年)": _safe_float(safe_row.get("payback_years", 0.0)) - _safe_float(common_row.get("payback_years", 0.0)),
        "IRR变化\n(百分点)": _safe_float(safe_row.get("irr_percent", 0.0)) - _safe_float(common_row.get("irr_percent", 0.0)),
        "安全评分变化": _safe_float(safe_row.get("safety_score", 0.0)) - _safe_float(common_row.get("safety_score", 0.0)),
    }
    labels = list(metrics.keys())
    vals = np.asarray(list(metrics.values()), dtype=float)
    colors = ["#4c78a8" if v >= 0 else "#b34b4b" for v in vals]
    order = np.arange(len(labels))[::-1]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.barh(order, vals, color=colors, alpha=0.88)
    ax.axvline(0.0, color="black", linewidth=0.8)
    ax.set_yticks(order)
    ax.set_yticklabels(labels)
    ax.grid(True, axis="x", linestyle="--", linewidth=0.6, alpha=0.28)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlabel("相对常用方案的变化量")
    ax.set_title(_pretty_title(scenario_name, "高安全相对常用方案增量对比"), pad=8)
    xpad = max(0.12, 0.04 * max(np.max(np.abs(vals)), 1.0))
    for i, v in zip(order, vals):
        ax.text(v + (xpad if v >= 0 else -xpad), i, f"{v:.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=8)
    fig.tight_layout(pad=0.9)
    save_path = output_dir / f"{_sanitize_filename(scenario_name)}_common_vs_high_safety_delta.png"
    fig.savefig(save_path, dpi=320, bbox_inches="tight")
    plt.close(fig)
    return str(save_path)


def save_scheme_comparison_bundle(scenario_name: str, common_row: Mapping[str, Any] | None, safe_row: Mapping[str, Any] | None, output_dir: str | Path = "outputs/reports/comparison") -> list[str]:
    if common_row is None or safe_row is None:
        return []
    output_dir = _ensure_dir(output_dir)
    return [
        _save_scheme_delta_csv(scenario_name, common_row, safe_row, output_dir),
        _save_scheme_delta_plot(scenario_name, common_row, safe_row, output_dir),
    ]
