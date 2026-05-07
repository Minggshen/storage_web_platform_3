
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(slots=True)
class StorageStrategy:
    strategy_id: str
    strategy_name: str

    vendor: str = ""
    chemistry: str = ""
    safety_level: str = "medium"
    cooling_mode: str = ""

    duration_min_h: float = 1.0
    duration_max_h: float = 4.0

    soc_min: float = 0.10
    soc_max: float = 0.90

    eta_charge: float = 0.95
    eta_discharge: float = 0.95

    c_rate_charge_max: float = 0.50
    c_rate_discharge_max: float = 0.50

    annual_cycle_limit: float = 0.0
    cycle_life_efc: float = 0.0
    degradation_cost_yuan_per_kwh_throughput: float = 0.0

    capex_energy_yuan_per_kwh: float = 0.0
    capex_power_yuan_per_kw: float = 0.0
    om_ratio_annual: float = 0.02
    replacement_year: int | None = None
    salvage_ratio: float = 0.05

    allow_service: bool = False
    allow_grid_charging: bool = True
    service_headroom_ratio: float = 0.15

    enabled: bool = True
    is_default_candidate: bool = True
    rated_power_kw_single: float = 0.0
    rated_energy_kwh_single: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)

    def duration_h(self, power_kw: float, energy_kwh: float) -> float:
        return float(energy_kwh / power_kw)

    def validate_candidate(self, power_kw: float, energy_kwh: float) -> list[str]:
        errors: list[str] = []
        if power_kw <= 0:
            errors.append("额定功率必须大于 0。")
        if energy_kwh <= 0:
            errors.append("额定容量必须大于 0。")
        if errors:
            return errors

        duration = self.duration_h(power_kw, energy_kwh)
        if duration < self.duration_min_h:
            errors.append(f"时长 {duration:.2f}h 低于策略下限 {self.duration_min_h:.2f}h。")
        if duration > self.duration_max_h:
            errors.append(f"时长 {duration:.2f}h 高于策略上限 {self.duration_max_h:.2f}h。")

        charge_limit_kw = energy_kwh * self.c_rate_charge_max
        discharge_limit_kw = energy_kwh * self.c_rate_discharge_max
        if power_kw > charge_limit_kw + 1e-9:
            errors.append(f"功率 {power_kw:.2f}kW 超过充电倍率约束上限 {charge_limit_kw:.2f}kW。")
        if power_kw > discharge_limit_kw + 1e-9:
            errors.append(f"功率 {power_kw:.2f}kW 超过放电倍率约束上限 {discharge_limit_kw:.2f}kW。")
        return errors


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def _safe_int_or_none(x: Any) -> int | None:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == "":
            return None
        return int(float(x))
    except Exception:
        return None


def _safe_bool(x: Any, default: bool = False) -> bool:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return default
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(int(x))
    text = str(x).strip().lower()
    if text in {"1", "true", "yes", "y", "是"}:
        return True
    if text in {"0", "false", "no", "n", "否"}:
        return False
    return default


def _find_main_header_row(df_raw: pd.DataFrame) -> int:
    for idx in range(min(20, len(df_raw))):
        vals = [str(x).strip() if x is not None else "" for x in df_raw.iloc[idx].tolist()]
        if "enabled" in vals and "manufacturer" in vals and "device_model" in vals and "rated_power_kw" in vals:
            return idx
    raise ValueError("未找到策略库主表表头行。")


def _read_main_sheet(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="储能策略与设备库", header=None)
    header_row = _find_main_header_row(raw)
    headers = [str(x).strip() if x is not None else "" for x in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 2:].copy()  # 跳过中文说明行
    df.columns = headers
    df = df.loc[~df.apply(lambda s: s.isna().all(), axis=1)].reset_index(drop=True)
    return df


def _read_ems_sheet(path: Path) -> dict[str, dict[str, Any]]:
    raw = pd.read_excel(path, sheet_name="EMS控制包库", header=None)
    header_row = None
    for idx in range(min(10, len(raw))):
        vals = [str(x).strip() if x is not None else "" for x in raw.iloc[idx].tolist()]
        if "ems_package_name" in vals and "capex_addon_yuan" in vals:
            header_row = idx
            break
    if header_row is None:
        return {}
    headers = [str(x).strip() if x is not None else "" for x in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 2:].copy()
    df.columns = headers
    df = df.loc[~df.apply(lambda s: s.isna().all(), axis=1)].reset_index(drop=True)

    out = {}
    for _, row in df.iterrows():
        name = str(row.get("ems_package_name", "")).strip()
        if not name:
            continue
        out[name] = row.to_dict()
    return out


def _map_safety_level(value: str) -> str:
    v = str(value).strip().lower()
    if v in {"a", "a-", "high", "高", "high_plus", "high_safe"}:
        return "high"
    if v in {"b+", "b", "medium", "中"}:
        return "medium"
    return "low"


def load_storage_strategies(
    file_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    sheet_name: str | int | None = 0,
) -> dict[str, StorageStrategy]:
    _ = sheet_name
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"设备策略库不存在：{path}")

    df = _read_main_sheet(path)
    ems_db = _read_ems_sheet(path)

    strategies: dict[str, StorageStrategy] = {}
    for _, row in df.iterrows():
        enabled = _safe_bool(row.get("enabled", 1), True)
        if not enabled:
            continue

        manufacturer = str(row.get("manufacturer", "")).strip()
        device_model = str(row.get("device_model", "")).strip()
        if not manufacturer or not device_model:
            continue

        strategy_id = f"{manufacturer}_{device_model}".replace(" ", "_")
        strategy_name = device_model
        ems_name = str(row.get("ems_package_name", "")).strip()
        ems_info = ems_db.get(ems_name, {})

        rated_power = _safe_float(row.get("rated_power_kw", 0.0), 0.0)
        rated_energy = _safe_float(row.get("rated_energy_kwh", 0.0), 0.0)
        duration_nominal = rated_energy / rated_power if rated_power > 0 else 2.0

        manual_grade = str(row.get("manual_safety_grade", row.get("cni_fit_level", "medium"))).strip()
        safety_level = _map_safety_level(manual_grade)

        eta = _safe_float(row.get("round_trip_efficiency", row.get("efficiency_pct", 95.0)), 95.0)
        eta = eta / 100.0 if eta > 1.5 else eta

        energy_price = _safe_float(row.get("energy_unit_price_yuan_per_kwh", row.get("capacity_price_yuan_per_kwh", 0.0)), 0.0)
        power_price = _safe_float(row.get("power_related_capex_yuan_per_kw", 0.0), 0.0)
        ems_capex_addon = _safe_float(ems_info.get("capex_addon_yuan", 0.0), 0.0)
        ems_maint = _safe_float(ems_info.get("annual_maintenance_yuan", 0.0), 0.0)

        base_capex = rated_energy * max(energy_price, 0.0) + rated_power * max(power_price, 0.0)
        om_ratio = _safe_float(row.get("annual_om_ratio", row.get("om_ratio_annual", 0.02)), 0.02)
        if ems_maint > 0 and base_capex > 1e-9:
            om_ratio += ems_maint / base_capex

        soc_min = _safe_float(row.get("soc_min", 0.10), 0.10)
        soc_max = _safe_float(row.get("soc_max", 0.90), 0.90)
        cycle_life_efc = _safe_float(row.get("cycle_life_efc", row.get("cycle_life", 0.0)), 0.0)
        annual_cycle_limit = _safe_float(row.get("annual_cycle_limit", 0.0), 0.0)

        strategy = StorageStrategy(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            vendor=manufacturer,
            chemistry=str(row.get("battery_chemistry", "")).strip(),
            safety_level=safety_level,
            cooling_mode=str(row.get("cooling_mode", row.get("thermal_management_type", ""))).strip(),
            duration_min_h=max(0.5, min(duration_nominal, _safe_float(row.get("duration_min_h", max(1.0, duration_nominal * 0.8)), max(1.0, duration_nominal * 0.8)))),
            duration_max_h=max(duration_nominal, _safe_float(row.get("duration_max_h", max(2.0, duration_nominal * 1.25)), max(2.0, duration_nominal * 1.25))),
            soc_min=soc_min,
            soc_max=max(soc_min + 0.05, soc_max),
            eta_charge=eta ** 0.5,
            eta_discharge=eta ** 0.5,
            c_rate_charge_max=_safe_float(row.get("c_rate_charge_max", row.get("max_charge_c_rate", max(0.25, rated_power / max(rated_energy,1e-9)))), max(0.25, rated_power / max(rated_energy,1e-9))),
            c_rate_discharge_max=_safe_float(row.get("c_rate_discharge_max", row.get("max_discharge_c_rate", max(0.25, rated_power / max(rated_energy,1e-9)))), max(0.25, rated_power / max(rated_energy,1e-9))),
            annual_cycle_limit=annual_cycle_limit,
            cycle_life_efc=max(0.0, cycle_life_efc),
            degradation_cost_yuan_per_kwh_throughput=_safe_float(row.get("degradation_cost_yuan_per_kwh_throughput", 0.0), 0.0),
            capex_energy_yuan_per_kwh=max(0.0, energy_price),
            capex_power_yuan_per_kw=max(0.0, power_price + ems_capex_addon / max(rated_power, 1.0)),
            om_ratio_annual=max(0.0, om_ratio),
            replacement_year=_safe_int_or_none(row.get("replacement_year", None)),
            salvage_ratio=_safe_float(row.get("salvage_ratio", 0.05), 0.05),
            allow_service=_safe_bool(row.get("supports_black_start", 1), True),
            allow_grid_charging=True,
            service_headroom_ratio=_safe_float(row.get("service_headroom_ratio", 0.15), 0.15),
            enabled=enabled,
            is_default_candidate=_safe_bool(row.get("is_default_candidate", 1), True),
            rated_power_kw_single=rated_power,
            rated_energy_kwh_single=rated_energy,
            metadata={
                "manufacturer": manufacturer,
                "device_model": device_model,
                "device_family": row.get("device_family"),
                "system_topology_type": row.get("system_topology_type"),
                "application_scene": row.get("application_scene"),
                "cni_fit_level": row.get("cni_fit_level"),
                "ems_package_name": ems_name,
                "ems_capex_addon_yuan": ems_capex_addon,
                "ems_annual_maintenance_yuan": ems_maint,
                "cycle_life_efc": max(0.0, cycle_life_efc),
            },
        )
        strategies[strategy.strategy_id] = strategy

    if not strategies:
        raise ValueError("策略库未解析出任何可用策略。")
    return strategies
