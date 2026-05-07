from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from services.file_store import read_table_file

MAP_REQUIRED_COLUMNS = ["date", "day_index", "internal_model_id", "external_model_id", "model_name"]
LIB_REQUIRED_COLUMNS = ["internal_model_id", "external_model_id", "model_name"] + [f"h{i:02d}" for i in range(24)]


def validate_runtime_files(
    year_map_path: Optional[Path],
    model_library_path: Optional[Path],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {
        "year_map_file": str(year_map_path) if year_map_path else None,
        "model_library_file": str(model_library_path) if model_library_path else None,
    }

    checks.append(
        {
            "name": "runtime 年映射文件存在",
            "ok": year_map_path is not None,
            "detail": year_map_path.name if year_map_path else "未找到 runtime_year_model_map 文件",
        }
    )
    checks.append(
        {
            "name": "runtime 模型库文件存在",
            "ok": model_library_path is not None,
            "detail": model_library_path.name if model_library_path else "未找到 runtime_model_library 文件",
        }
    )

    if year_map_path is None or model_library_path is None:
        return checks, summaries

    map_df = read_table_file(year_map_path)
    lib_df = read_table_file(model_library_path)

    missing_map_cols = [c for c in MAP_REQUIRED_COLUMNS if c not in map_df.columns]
    missing_lib_cols = [c for c in LIB_REQUIRED_COLUMNS if c not in lib_df.columns]

    checks.append(
        {
            "name": "年映射表字段完整",
            "ok": len(missing_map_cols) == 0,
            "detail": "字段完整" if not missing_map_cols else f"缺少列：{', '.join(missing_map_cols)}",
        }
    )
    checks.append(
        {
            "name": "模型库字段完整",
            "ok": len(missing_lib_cols) == 0,
            "detail": "字段完整" if not missing_lib_cols else f"缺少列：{', '.join(missing_lib_cols)}",
        }
    )

    if missing_map_cols or missing_lib_cols:
        return checks, summaries

    map_df["date"] = pd.to_datetime(map_df["date"], errors="coerce")
    map_df["internal_model_id"] = pd.to_numeric(map_df["internal_model_id"], errors="coerce")
    lib_df["internal_model_id"] = pd.to_numeric(lib_df["internal_model_id"], errors="coerce")

    date_ok = map_df["date"].notna().all()
    checks.append(
        {
            "name": "年映射日期可解析",
            "ok": bool(date_ok),
            "detail": "日期列可解析" if date_ok else "date 列存在无法解析值",
        }
    )

    map_sorted = map_df.sort_values("date").reset_index(drop=True)
    date_diffs = map_sorted["date"].diff().dropna()
    continuous_ok = bool((date_diffs == pd.Timedelta(days=1)).all()) if not date_diffs.empty else False
    checks.append(
        {
            "name": "年映射日期连续",
            "ok": continuous_ok,
            "detail": "日期按天连续" if continuous_ok else "日期不是严格逐天连续",
        }
    )

    row365_ok = len(map_df) == 365
    checks.append(
        {
            "name": "年映射 365 天",
            "ok": row365_ok,
            "detail": f"当前 {len(map_df)} 天",
        }
    )

    duplicate_dates = int(map_df["date"].duplicated().sum())
    checks.append(
        {
            "name": "年映射日期无重复",
            "ok": duplicate_dates == 0,
            "detail": "日期无重复" if duplicate_dates == 0 else f"重复日期数：{duplicate_dates}",
        }
    )

    duplicate_model_ids = int(lib_df["internal_model_id"].duplicated().sum())
    checks.append(
        {
            "name": "模型库 internal_model_id 唯一",
            "ok": duplicate_model_ids == 0,
            "detail": "模型 ID 无重复" if duplicate_model_ids == 0 else f"重复 internal_model_id 数：{duplicate_model_ids}",
        }
    )

    map_model_ids = set(map_df["internal_model_id"].dropna().astype(int))
    lib_model_ids = set(lib_df["internal_model_id"].dropna().astype(int))
    model_cross_ok = map_model_ids.issubset(lib_model_ids)
    missing_ids = sorted(map_model_ids - lib_model_ids)
    checks.append(
        {
            "name": "年映射模型 ID 能在模型库找到",
            "ok": model_cross_ok,
            "detail": "全部可匹配" if model_cross_ok else f"缺少模型 ID：{missing_ids}",
        }
    )

    hour_cols = [f"h{i:02d}" for i in range(24)]
    numeric_hours = lib_df[hour_cols].apply(pd.to_numeric, errors="coerce")
    hour_ok = numeric_hours.notna().all().all()
    checks.append(
        {
            "name": "模型库 24 点曲线完整",
            "ok": bool(hour_ok),
            "detail": "h00~h23 全部为数值" if hour_ok else "某些小时列存在缺失或非数值",
        }
    )

    summaries.update(
        {
            "map_rows": int(len(map_df)),
            "library_rows": int(len(lib_df)),
            "start_date": str(map_sorted["date"].min().date()) if date_ok else None,
            "end_date": str(map_sorted["date"].max().date()) if date_ok else None,
            "model_count": int(lib_df["internal_model_id"].nunique()),
        }
    )

    return checks, summaries