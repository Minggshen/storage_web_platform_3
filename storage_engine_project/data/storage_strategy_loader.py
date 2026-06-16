
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from storage_engine_project.optimization.device_safety_scoring import (
    DeviceSafetyConfig,
    DeviceSafetyScores,
    has_device_safety_sheets,
    normalize_device_safety_weights,
    read_device_safety_config,
    score_device,
)

V2_SCHEMA_VERSION = "device_library_v2"
V2_REQUIRED_SHEETS = {"元数据", "设备库", "安全权重", "安全评分规则"}
V2_DEVICE_COLUMNS = [
    "enabled",
    "manufacturer",
    "device_model",
    "rated_power_kw",
    "rated_energy_kwh",
    "duration_hour",
    "battery_chemistry",
    "cooling_class",
    "cooling_note",
    "ip_system",
    "ip_pack",
    "ip_pcs",
    "corrosion_grade",
    "corrosion_optional_grade",
    "manual_safety_grade",
    "round_trip_efficiency",
    "c_rate_charge_max",
    "c_rate_discharge_max",
    "energy_unit_price_yuan_per_kwh",
    "power_related_capex_yuan_per_kw",
    "annual_om_ratio",
    "soc_min",
    "soc_max",
    "operating_temp_min_c",
    "operating_temp_max_c",
    "cycle_life",
    "fire_detection_class",
    "fire_suppression_class",
    "explosion_protection_class",
    "propagation_protection_class",
    "ems_model",
    "certification_tokens",
    "weight_kg",
    "dimensions_mm",
    "is_default_candidate",
    "ems_package_name",
]


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

    device_safety_available: bool = False
    device_safety_sub_scores: dict[str, float] = field(default_factory=dict)
    device_safety_weighted_score: float = 0.0
    device_safety_cost: float = 0.5
    device_safety_trace: dict[str, list[str]] = field(default_factory=dict)
    device_safety_data_quality_flags: list[str] = field(default_factory=list)

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


def _read_metadata_value(path: Path, key: str) -> str:
    try:
        metadata = pd.read_excel(path, sheet_name="元数据")
    except Exception as exc:
        raise ValueError("设备策略库必须使用 v2 模板，缺少 元数据 Sheet。") from exc
    metadata.columns = [str(x).strip() if x is not None else "" for x in metadata.columns]
    if "key" not in metadata.columns or "value" not in metadata.columns:
        raise ValueError("设备策略库 元数据 Sheet 必须包含 key/value 列。")
    for _, row in metadata.iterrows():
        if str(row.get("key") or "").strip() == key:
            return str(row.get("value") or "").strip()
    return ""


def _assert_v2_workbook(path: Path) -> None:
    xl = pd.ExcelFile(path)
    missing_sheets = sorted(V2_REQUIRED_SHEETS - set(xl.sheet_names))
    if missing_sheets:
        raise ValueError(f"设备策略库必须使用 {V2_SCHEMA_VERSION} 模板，缺少 Sheet：{missing_sheets}")
    schema_version = _read_metadata_value(path, "schema_version")
    if schema_version != V2_SCHEMA_VERSION:
        raise ValueError(
            f"设备策略库 schema_version 必须为 {V2_SCHEMA_VERSION}，当前为 {schema_version or '空'}。"
        )


def _read_main_sheet(path: Path) -> pd.DataFrame:
    _assert_v2_workbook(path)
    df = pd.read_excel(path, sheet_name="设备库")
    df.columns = [str(x).strip() if x is not None else "" for x in df.columns]
    missing_columns = sorted(set(V2_DEVICE_COLUMNS) - set(df.columns))
    if missing_columns:
        raise ValueError(f"设备策略库 设备库 Sheet 缺少 v2 字段：{missing_columns}")
    return df.loc[~df.apply(lambda s: s.isna().all(), axis=1)].reset_index(drop=True)


def _map_safety_level(value: str) -> str:
    v = str(value).strip().lower()
    if v in {"a", "a-", "high", "高", "high_plus", "high_safe"}:
        return "high"
    if v in {"b+", "b", "medium", "中"}:
        return "medium"
    return "low"


def _load_device_safety_config(
    path: Path,
    device_safety_metric_weights: dict[str, float] | None = None,
) -> DeviceSafetyConfig | None:
    if not has_device_safety_sheets(path):
        return None
    config = read_device_safety_config(path)
    if not device_safety_metric_weights:
        return config
    overrides = {
        key: float(value)
        for key, value in device_safety_metric_weights.items()
        if key in config.weights
    }
    if not overrides or sum(max(0.0, value) for value in overrides.values()) <= 1e-12:
        return config
    weights = dict(config.weights)
    weights.update(overrides)
    return DeviceSafetyConfig(
        weights=normalize_device_safety_weights(weights, dimensions=config.dimensions),
        rules=config.rules,
        labels=config.labels,
    )


def _score_device_safety(
    row: dict[str, Any],
    config: DeviceSafetyConfig | None,
    *,
    strategy_label: str,
) -> DeviceSafetyScores | None:
    if config is None:
        return None
    try:
        return score_device(row, config)
    except Exception as exc:
        raise ValueError(f"设备 {strategy_label} 安全评分失败：{exc}") from exc


def load_storage_strategies(
    file_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    sheet_name: str | int | None = 0,
    device_safety_metric_weights: dict[str, float] | None = None,
) -> dict[str, StorageStrategy]:
    _ = sheet_name
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"设备策略库不存在：{path}")

    df = _read_main_sheet(path)
    device_safety_config = _load_device_safety_config(path, device_safety_metric_weights)

    strategies: dict[str, StorageStrategy] = {}
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        enabled = _safe_bool(row.get("enabled", 1), True)
        if not enabled:
            continue

        manufacturer = str(row.get("manufacturer", "")).strip()
        device_model = str(row.get("device_model", "")).strip()
        if not manufacturer or not device_model:
            continue

        strategy_id = f"{manufacturer}_{device_model}".replace(" ", "_")
        strategy_name = device_model
        device_safety = _score_device_safety(
            row_dict,
            device_safety_config,
            strategy_label=strategy_id,
        )
        ems_name = str(row.get("ems_package_name", "")).strip()

        rated_power = _safe_float(row.get("rated_power_kw", 0.0), 0.0)
        rated_energy = _safe_float(row.get("rated_energy_kwh", 0.0), 0.0)
        duration_nominal = rated_energy / rated_power if rated_power > 0 else 2.0

        manual_grade = str(row.get("manual_safety_grade", "")).strip()
        safety_level = _map_safety_level(manual_grade)

        eta = _safe_float(row.get("round_trip_efficiency", 0.95), 0.95)
        if eta <= 0 or eta > 1.0:
            raise ValueError(f"设备 {strategy_id} 的 round_trip_efficiency 必须按 0~1 小数填写。")

        energy_price = _safe_float(row.get("energy_unit_price_yuan_per_kwh", 0.0), 0.0)
        power_price = _safe_float(row.get("power_related_capex_yuan_per_kw", 0.0), 0.0)
        ems_capex_addon = 0.0
        ems_maint = 0.0

        base_capex = rated_energy * max(energy_price, 0.0) + rated_power * max(power_price, 0.0)
        om_ratio = _safe_float(row.get("annual_om_ratio", 0.02), 0.02)
        if ems_maint > 0 and base_capex > 1e-9:
            om_ratio += ems_maint / base_capex

        soc_min = _safe_float(row.get("soc_min", 0.10), 0.10)
        soc_max = _safe_float(row.get("soc_max", 0.90), 0.90)
        cycle_life_efc = _safe_float(row.get("cycle_life", 0.0), 0.0)
        annual_cycle_limit = _safe_float(row.get("annual_cycle_limit", 0.0), 0.0)

        strategy = StorageStrategy(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            vendor=manufacturer,
            chemistry=str(row.get("battery_chemistry", "")).strip(),
            safety_level=safety_level,
            cooling_mode=str(row.get("cooling_class", "")).strip(),
            duration_min_h=max(0.5, min(duration_nominal, _safe_float(row.get("duration_min_h", max(1.0, duration_nominal * 0.8)), max(1.0, duration_nominal * 0.8)))),
            duration_max_h=max(duration_nominal, _safe_float(row.get("duration_max_h", max(2.0, duration_nominal * 1.25)), max(2.0, duration_nominal * 1.25))),
            soc_min=soc_min,
            soc_max=max(soc_min + 0.05, soc_max),
            eta_charge=eta ** 0.5,
            eta_discharge=eta ** 0.5,
            c_rate_charge_max=_safe_float(row.get("c_rate_charge_max", max(0.25, rated_power / max(rated_energy, 1e-9))), max(0.25, rated_power / max(rated_energy, 1e-9))),
            c_rate_discharge_max=_safe_float(row.get("c_rate_discharge_max", max(0.25, rated_power / max(rated_energy, 1e-9))), max(0.25, rated_power / max(rated_energy, 1e-9))),
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
            device_safety_available=device_safety is not None,
            device_safety_sub_scores=dict(device_safety.sub_scores) if device_safety else {},
            device_safety_weighted_score=float(device_safety.weighted_score) if device_safety else 0.0,
            device_safety_cost=float(device_safety.device_safety_cost) if device_safety else 0.5,
            device_safety_trace={k: list(v) for k, v in device_safety.trace.items()} if device_safety else {},
            device_safety_data_quality_flags=list(device_safety.data_quality_flags) if device_safety else [],
            metadata={
                "manufacturer": manufacturer,
                "device_model": device_model,
                "manual_safety_grade": manual_grade,
                "cooling_class": row.get("cooling_class"),
                "cooling_note": row.get("cooling_note"),
                "ip_system": row.get("ip_system"),
                "ip_pack": row.get("ip_pack"),
                "ip_pcs": row.get("ip_pcs"),
                "corrosion_grade": row.get("corrosion_grade"),
                "corrosion_optional_grade": row.get("corrosion_optional_grade"),
                "fire_detection_class": row.get("fire_detection_class"),
                "fire_suppression_class": row.get("fire_suppression_class"),
                "explosion_protection_class": row.get("explosion_protection_class"),
                "propagation_protection_class": row.get("propagation_protection_class"),
                "ems_model": row.get("ems_model"),
                "certification_tokens": row.get("certification_tokens"),
                "weight_kg": row.get("weight_kg"),
                "dimensions_mm": row.get("dimensions_mm"),
                "ems_package_name": ems_name,
                "ems_capex_addon_yuan": ems_capex_addon,
                "ems_annual_maintenance_yuan": ems_maint,
                "cycle_life_efc": max(0.0, cycle_life_efc),
                "device_safety_available": bool(device_safety is not None),
                "device_safety_weighted_score": float(device_safety.weighted_score) if device_safety else 0.0,
                "device_safety_cost": float(device_safety.device_safety_cost) if device_safety else 0.5,
                "device_safety_data_quality_flags": list(device_safety.data_quality_flags) if device_safety else [],
            },
        )
        strategies[strategy.strategy_id] = strategy

    if not strategies:
        raise ValueError("策略库未解析出任何可用策略。")
    return strategies
