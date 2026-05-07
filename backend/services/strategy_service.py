from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from services.file_store import read_table_file

CONTROL_REQUIRED_KEYS = {"优化偏好模式", "经济权重", "安全权重", "最低安全分门槛", "默认EMS控制包"}

DEVICE_REQUIRED_COLUMNS = {
    "enabled",
    "manufacturer",
    "series_name",
    "device_model",
    "device_family",
    "system_topology_type",
    "application_scene",
    "cni_fit_level",
    "is_default_candidate",
    "ems_package_name",
    "rated_power_kw",
    "rated_energy_kwh",
    "duration_h",
    "manual_safety_grade",
    "energy_unit_price_yuan_per_kwh",
    "power_related_capex_yuan_per_kw",
}

EMS_REQUIRED_COLUMNS = {
    "ems_package_name",
    "ems_model",
    "cyber_security_mode",
    "certificate_management",
    "public_key_import",
    "remote_maintenance",
    "anti_backfeed",
    "overload_protection",
    "backup_power",
    "soc_protection",
}


def validate_strategy_library(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    main_raw = read_table_file(file_path, sheet_name="储能策略与设备库", header=None)
    ems_raw = read_table_file(file_path, sheet_name="EMS控制包库", header=None)

    checks: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}

    control_keys = set(main_raw.iloc[2:9, 0].dropna().astype(str).str.strip())
    missing_control = sorted(CONTROL_REQUIRED_KEYS - control_keys)
    checks.append(
        {
            "name": "策略控制参数完整",
            "ok": len(missing_control) == 0,
            "detail": "控制参数完整" if not missing_control else f"缺少控制项：{missing_control}",
        }
    )

    device_headers = [str(v).strip() for v in main_raw.iloc[11].tolist()]
    device_df = main_raw.iloc[13:].copy()
    device_df.columns = device_headers
    device_df = device_df.dropna(how="all").reset_index(drop=True)

    missing_device_cols = sorted(DEVICE_REQUIRED_COLUMNS - set(device_df.columns))
    checks.append(
        {
            "name": "设备主表字段完整",
            "ok": len(missing_device_cols) == 0,
            "detail": "设备主表字段完整" if not missing_device_cols else f"缺少字段：{missing_device_cols}",
        }
    )

    ems_headers = [str(v).strip() for v in ems_raw.iloc[2].tolist()]
    ems_df = ems_raw.iloc[4:].copy()
    ems_df.columns = ems_headers
    ems_df = ems_df.dropna(how="all").reset_index(drop=True)

    missing_ems_cols = sorted(EMS_REQUIRED_COLUMNS - set(ems_df.columns))
    checks.append(
        {
            "name": "EMS 包字段完整",
            "ok": len(missing_ems_cols) == 0,
            "detail": "EMS 字段完整" if not missing_ems_cols else f"缺少字段：{missing_ems_cols}",
        }
    )

    enabled_count = (
        int(pd.to_numeric(device_df.get("enabled"), errors="coerce").fillna(0).sum())
        if "enabled" in device_df.columns
        else 0
    )
    checks.append({"name": "设备主表记录存在", "ok": len(device_df) > 0, "detail": f"当前 {len(device_df)} 条设备记录"})
    checks.append({"name": "至少存在启用设备", "ok": enabled_count > 0, "detail": f"当前启用设备数：{enabled_count}"})

    if "ems_package_name" in device_df.columns and "ems_package_name" in ems_df.columns:
        missing_ems_ref = sorted(
            set(device_df["ems_package_name"].dropna().astype(str)) - set(ems_df["ems_package_name"].dropna().astype(str))
        )
        checks.append(
            {
                "name": "设备表 EMS 包可匹配",
                "ok": len(missing_ems_ref) == 0,
                "detail": "设备表 EMS 包均能在 EMS 库找到" if not missing_ems_ref else f"缺少 EMS 包：{missing_ems_ref}",
            }
        )

    numeric_cols = [
        "rated_power_kw",
        "rated_energy_kwh",
        "duration_h",
        "energy_unit_price_yuan_per_kwh",
        "power_related_capex_yuan_per_kw",
    ]
    numeric_ok = True
    for col in numeric_cols:
        if col in device_df.columns:
            if pd.to_numeric(device_df[col], errors="coerce").notna().sum() == 0:
                numeric_ok = False
                break

    checks.append(
        {
            "name": "设备关键数值列可解析",
            "ok": numeric_ok,
            "detail": "功率/容量/价格字段可解析" if numeric_ok else "存在关键数值列无法解析",
        }
    )

    summaries.update(
        {
            "device_rows": int(len(device_df)),
            "enabled_device_rows": enabled_count,
            "ems_rows": int(len(ems_df)),
            "manufacturers": sorted(device_df["manufacturer"].dropna().astype(str).unique().tolist())
            if "manufacturer" in device_df.columns
            else [],
            "default_ems_package": str(main_raw.iloc[8, 1]) if main_raw.shape[0] > 8 and main_raw.shape[1] > 1 else None,
        }
    )

    return checks, summaries