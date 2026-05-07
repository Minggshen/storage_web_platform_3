from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.data.storage_strategy_loader import StorageStrategy


def _positive_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except Exception:
        return None
    if not np.isfinite(number) or number <= 0:
        return None
    return float(number)


def _bool_from_meta(meta: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key not in meta:
            continue
        value = meta.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and np.isfinite(float(value)):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "是", "允许", "启用"}:
            return True
        if text in {"0", "false", "no", "n", "off", "否", "不允许", "停用"}:
            return False
    return bool(default)


@dataclass(slots=True)
class StorageConfigurationBoundary:
    strategy_id: str
    is_feasible: bool

    power_min_kw: float
    power_max_kw: float
    duration_min_h: float
    duration_max_h: float
    energy_min_kwh: float
    energy_max_kwh: float

    peak_import_kw: float
    annual_import_kwh: float
    mean_daily_import_kwh: float
    max_daily_import_kwh: float
    max_pv_surplus_kw: float
    transformer_active_power_limit_kw: float | None
    max_transformer_charge_headroom_kw: float | None

    allow_grid_export: bool
    allow_grid_charging: bool
    limiting_factors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "is_feasible": bool(self.is_feasible),
            "power_min_kw": float(self.power_min_kw),
            "power_max_kw": float(self.power_max_kw),
            "duration_min_h": float(self.duration_min_h),
            "duration_max_h": float(self.duration_max_h),
            "energy_min_kwh": float(self.energy_min_kwh),
            "energy_max_kwh": float(self.energy_max_kwh),
            "peak_import_kw": float(self.peak_import_kw),
            "annual_import_kwh": float(self.annual_import_kwh),
            "mean_daily_import_kwh": float(self.mean_daily_import_kwh),
            "max_daily_import_kwh": float(self.max_daily_import_kwh),
            "max_pv_surplus_kw": float(self.max_pv_surplus_kw),
            "transformer_active_power_limit_kw": self.transformer_active_power_limit_kw,
            "max_transformer_charge_headroom_kw": self.max_transformer_charge_headroom_kw,
            "allow_grid_export": bool(self.allow_grid_export),
            "allow_grid_charging": bool(self.allow_grid_charging),
            "limiting_factors": list(self.limiting_factors),
            "notes": list(self.notes),
            "errors": list(self.errors),
        }


def compute_storage_configuration_boundary(
    ctx: AnnualOperationContext,
    strategy: StorageStrategy,
    *,
    explicit_power_min_kw: float | None = None,
    explicit_power_max_kw: float | None = None,
    grid_interconnection_limit_kw: float | None = None,
    explicit_duration_min_h: float | None = None,
    explicit_duration_max_h: float | None = None,
) -> StorageConfigurationBoundary:
    meta = dict(ctx.meta)
    net_load = np.asarray(ctx.net_load_matrix_kw, dtype=float)
    import_kw = np.maximum(net_load, 0.0)
    daily_import_kwh = np.sum(import_kw, axis=1)

    peak_import_kw = float(np.max(import_kw)) if import_kw.size else 0.0
    annual_import_kwh = float(np.sum(import_kw))
    mean_daily_import_kwh = float(np.mean(daily_import_kwh)) if daily_import_kwh.size else 0.0
    max_daily_import_kwh = float(np.max(daily_import_kwh)) if daily_import_kwh.size else 0.0
    max_pv_surplus_kw = float(np.max(np.maximum(-net_load, 0.0))) if net_load.size else 0.0
    transformer_limit_kw = ctx.transformer_active_power_limit_kw

    max_charge_headroom_kw: float | None = None
    if transformer_limit_kw is not None and import_kw.size:
        headroom = float(np.max(np.maximum(float(transformer_limit_kw) - import_kw, 0.0)))
        max_charge_headroom_kw = max(0.0, headroom)

    allow_grid_export = _bool_from_meta(
        meta,
        "allow_grid_export",
        "allow_reverse_power_to_grid",
        "allow_export_to_grid",
        default=False,
    )
    allow_grid_charging = bool(getattr(strategy, "allow_grid_charging", True))

    c_rate_duration_min = 0.0
    if float(strategy.c_rate_charge_max) > 1e-9:
        c_rate_duration_min = max(c_rate_duration_min, 1.0 / float(strategy.c_rate_charge_max))
    if float(strategy.c_rate_discharge_max) > 1e-9:
        c_rate_duration_min = max(c_rate_duration_min, 1.0 / float(strategy.c_rate_discharge_max))

    duration_min = max(float(strategy.duration_min_h), c_rate_duration_min)
    duration_max = float(strategy.duration_max_h)
    requested_duration_min = _positive_or_none(explicit_duration_min_h)
    requested_duration_max = _positive_or_none(explicit_duration_max_h)
    if requested_duration_min is not None:
        duration_min = max(duration_min, requested_duration_min)
    if requested_duration_max is not None:
        duration_max = min(duration_max, requested_duration_max)

    notes: list[str] = []
    errors: list[str] = []
    limiting_factors: list[str] = []

    upper_candidates: list[tuple[str, float]] = []
    explicit_power_max = _positive_or_none(explicit_power_max_kw)
    grid_limit = _positive_or_none(grid_interconnection_limit_kw)
    if explicit_power_max is not None:
        upper_candidates.append(("device_power_max_kw", explicit_power_max))
    if grid_limit is not None:
        upper_candidates.append(("grid_interconnection_limit_kw", grid_limit))
    if transformer_limit_kw is not None and transformer_limit_kw > 0:
        upper_candidates.append(("transformer_active_power_limit_kw", float(transformer_limit_kw)))
    if not allow_grid_export and peak_import_kw > 0:
        upper_candidates.append(("target_peak_import_kw_no_export", peak_import_kw))

    single_power = _positive_or_none(getattr(strategy, "rated_power_kw_single", None))
    if not upper_candidates and single_power is not None:
        upper_candidates.append(("catalog_single_unit_power_kw", single_power))
        notes.append("未设置并网、变压器或负荷吸纳功率上限，使用设备库单套额定功率作为保守搜索上限。")

    if not upper_candidates:
        errors.append("缺少可计算功率上限的数据：需要设备上限、并网上限、变压器上限、目标负荷峰值或设备单套额定功率。")
        power_max = 0.0
    else:
        source, power_max = min(upper_candidates, key=lambda item: item[1])
        limiting_factors.append(source)

    requested_power_min = _positive_or_none(explicit_power_min_kw)
    if requested_power_min is not None:
        power_min = requested_power_min
        limiting_factors.append("search_power_min_kw")
    else:
        power_min = min(power_max, 1.0) if power_max > 0 else 0.0
        notes.append("未设置 search_power_min_kw，使用 1 kW 作为数值搜索下限；工程推荐下限应由项目侧显式给定。")

    if power_max <= 0:
        errors.append("计算得到的储能功率上限不大于 0。")
    if power_min > power_max > 0:
        errors.append(f"显式最小功率 {power_min:.4f} kW 大于配置功率上限 {power_max:.4f} kW。")

    if duration_max < duration_min:
        errors.append(f"时长上限 {duration_max:.4f} h 小于由设备倍率/策略得到的时长下限 {duration_min:.4f} h。")

    soc_window = max(0.0, float(strategy.soc_max) - float(strategy.soc_min))
    energy_min = max(0.0, power_min * duration_min)
    energy_max_from_power_duration = max(0.0, power_max * duration_max)
    energy_max = energy_max_from_power_duration

    if not allow_grid_export and max_daily_import_kwh > 0 and soc_window > 1e-9:
        daily_absorption_rated_energy_cap = max_daily_import_kwh / soc_window
        if daily_absorption_rated_energy_cap < energy_max:
            energy_max = daily_absorption_rated_energy_cap
            limiting_factors.append("max_daily_import_kwh_no_export_soc_window")
            notes.append("禁止反送电时，额定容量上限按最大日用电量除以可用 SOC 窗口收紧。")

    if energy_min > energy_max > 0:
        errors.append(f"最小容量 {energy_min:.4f} kWh 大于配置容量上限 {energy_max:.4f} kWh。")

    if not allow_grid_charging and max_pv_surplus_kw <= 1e-9:
        errors.append("当前策略禁止电网充电，但目标用户没有可用于充电的 PV 余电。")

    is_feasible = not errors
    return StorageConfigurationBoundary(
        strategy_id=str(strategy.strategy_id),
        is_feasible=is_feasible,
        power_min_kw=float(power_min),
        power_max_kw=float(power_max),
        duration_min_h=float(duration_min),
        duration_max_h=float(duration_max),
        energy_min_kwh=float(energy_min),
        energy_max_kwh=float(energy_max),
        peak_import_kw=float(peak_import_kw),
        annual_import_kwh=float(annual_import_kwh),
        mean_daily_import_kwh=float(mean_daily_import_kwh),
        max_daily_import_kwh=float(max_daily_import_kwh),
        max_pv_surplus_kw=float(max_pv_surplus_kw),
        transformer_active_power_limit_kw=None if transformer_limit_kw is None else float(transformer_limit_kw),
        max_transformer_charge_headroom_kw=max_charge_headroom_kw,
        allow_grid_export=bool(allow_grid_export),
        allow_grid_charging=bool(allow_grid_charging),
        limiting_factors=limiting_factors,
        notes=notes,
        errors=errors,
    )
