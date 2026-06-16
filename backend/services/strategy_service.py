from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from services.file_store import read_table_file

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
V2_NUMERIC_COLUMNS = [
    "enabled",
    "rated_power_kw",
    "rated_energy_kwh",
    "duration_hour",
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
    "weight_kg",
    "is_default_candidate",
]


def validate_strategy_library(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sheet_names = _excel_sheet_names(file_path)
    checks: List[Dict[str, Any]] = []
    if not sheet_names:
        checks.append(
            {
                "name": "策略库格式",
                "ok": False,
                "detail": "设备策略库必须使用 v2 模板 .xlsx/.xlsm 文件。",
            }
        )
        return checks, _empty_summary()
    return _validate_v2_strategy_library(file_path)


def _validate_v2_strategy_library(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sheet_names = set(_excel_sheet_names(file_path))
    checks: List[Dict[str, Any]] = []
    missing_sheets = sorted(V2_REQUIRED_SHEETS - sheet_names)
    schema_version = _read_metadata_value(file_path, "schema_version") if "元数据" in sheet_names else ""
    is_v2 = not missing_sheets and schema_version == V2_SCHEMA_VERSION
    checks.append(
        {
            "name": "策略库格式",
            "ok": is_v2,
            "detail": "检测到 device_library_v2 模板"
            if is_v2
            else (
                f"必须使用 device_library_v2 模板；缺少 Sheet：{missing_sheets or '无'}；"
                f"schema_version：{schema_version or '未找到'}"
            ),
        }
    )
    if "设备库" not in sheet_names:
        return checks, _empty_summary()

    device_df = read_table_file(file_path, sheet_name="设备库", header=0)
    device_df.columns = [str(v).strip() for v in device_df.columns]
    device_df = device_df.dropna(how="all").reset_index(drop=True)

    missing_device_cols = sorted(set(V2_DEVICE_COLUMNS) - set(device_df.columns))
    checks.append(
        {
            "name": "设备主表字段完整",
            "ok": not missing_device_cols,
            "detail": "设备主表 v2 字段完整" if not missing_device_cols else f"缺少字段：{missing_device_cols}",
        }
    )

    enabled_count = _enabled_count(device_df)
    checks.append({"name": "设备主表记录存在", "ok": len(device_df) > 0, "detail": f"当前 {len(device_df)} 条设备记录"})
    checks.append({"name": "至少存在启用设备", "ok": enabled_count > 0, "detail": f"当前启用设备数：{enabled_count}"})

    numeric_ok = not missing_device_cols and _numeric_columns_parse_exact(device_df, V2_NUMERIC_COLUMNS)
    checks.append(
        {
            "name": "设备关键数值列可解析",
            "ok": numeric_ok,
            "detail": "功率/容量/效率/价格字段可解析" if numeric_ok else "存在关键数值列无法解析",
        }
    )
    efficiency_ok = _range_column(device_df, "round_trip_efficiency", lower=0.0, upper=1.0)
    checks.append(
        {
            "name": "往返效率范围",
            "ok": efficiency_ok,
            "detail": "round_trip_efficiency 已按 0~1 小数填写" if efficiency_ok else "round_trip_efficiency 必须按 0~1 小数填写",
        }
    )
    soc_ok = _range_column(device_df, "soc_min", lower=0.0, upper=1.0) and _range_column(
        device_df,
        "soc_max",
        lower=0.0,
        upper=1.0,
    )
    checks.append(
        {
            "name": "SOC 范围",
            "ok": soc_ok,
            "detail": "soc_min/soc_max 已按 0~1 小数填写" if soc_ok else "soc_min/soc_max 必须按 0~1 小数填写",
        }
    )

    safety_summary: Dict[str, Any] = {
        "safety_sheets_present": not missing_sheets,
        "safety_rule_count": 0,
        "device_safety_score_min": None,
        "device_safety_score_max": None,
        "safety_rule_flags": [],
    }
    missing_safety_sheets = sorted({"安全权重", "安全评分规则"} - sheet_names)
    checks.append(
        {
            "name": "设备安全评分 Sheet",
            "ok": not missing_safety_sheets,
            "detail": "已包含 安全权重/安全评分规则"
            if not missing_safety_sheets
            else f"缺少设备安全评分 Sheet：{missing_safety_sheets}",
        }
    )
    if not missing_safety_sheets and not missing_device_cols:
        try:
            from storage_engine_project.optimization.device_safety_scoring import (
                read_device_safety_config,
                score_device_library,
            )

            config = read_device_safety_config(file_path)
            scores, flags = score_device_library(device_df.to_dict("records"), config)
            score_values = [float(item.weighted_score) for item in scores]
            safety_summary = {
                "safety_sheets_present": True,
                "safety_rule_count": len(config.rules),
                "device_safety_score_min": min(score_values) if score_values else None,
                "device_safety_score_max": max(score_values) if score_values else None,
                "safety_rule_flags": flags,
            }
            checks.append(
                {
                    "name": "设备安全评分规则可解析",
                    "ok": True,
                    "detail": f"解析规则 {len(config.rules)} 条，规则覆盖提示 {len(flags)} 条",
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "设备安全评分规则可解析",
                    "ok": False,
                    "detail": f"设备安全评分规则解析失败：{exc}",
                }
            )

    ems_values = (
        device_df["ems_package_name"].dropna().astype(str).map(str.strip).replace("", pd.NA).dropna().tolist()
        if "ems_package_name" in device_df.columns
        else []
    )
    summaries: Dict[str, Any] = {
        "device_rows": int(len(device_df)),
        "enabled_device_rows": enabled_count,
        "ems_rows": 0,
        "manufacturers": sorted(device_df["manufacturer"].dropna().astype(str).unique().tolist())
        if "manufacturer" in device_df.columns
        else [],
        "default_ems_package": ems_values[0] if ems_values else None,
        **safety_summary,
    }
    return checks, summaries


def _excel_sheet_names(file_path: Path) -> set[str]:
    suffix = file_path.suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        return set()
    return set(pd.ExcelFile(file_path).sheet_names)


def _read_metadata_value(file_path: Path, key: str) -> str:
    try:
        metadata = read_table_file(file_path, sheet_name="元数据", header=0)
    except Exception:
        return ""
    metadata.columns = [str(value).strip() for value in metadata.columns]
    if "key" not in metadata.columns or "value" not in metadata.columns:
        return ""
    for _, row in metadata.iterrows():
        if str(row.get("key") or "").strip() == key:
            return str(row.get("value") or "").strip()
    return ""


def _enabled_count(df: pd.DataFrame) -> int:
    if "enabled" not in df.columns:
        return 0
    return int(pd.to_numeric(df["enabled"], errors="coerce").fillna(0).sum())


def _numeric_columns_parse_exact(df: pd.DataFrame, columns: list[str]) -> bool:
    for column in columns:
        if column not in df.columns:
            return False
        if pd.to_numeric(df[column], errors="coerce").notna().sum() == 0:
            return False
    return True


def _range_column(df: pd.DataFrame, column: str, *, lower: float, upper: float) -> bool:
    if column not in df.columns:
        return False
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if values.empty:
        return False
    return bool(((values > lower) & (values <= upper)).all())


def _empty_summary() -> Dict[str, Any]:
    return {
        "device_rows": 0,
        "enabled_device_rows": 0,
        "ems_rows": 0,
        "manufacturers": [],
        "default_ems_package": None,
        "safety_sheets_present": False,
        "safety_rule_count": 0,
        "device_safety_score_min": None,
        "device_safety_score_max": None,
        "safety_rule_flags": [],
    }
