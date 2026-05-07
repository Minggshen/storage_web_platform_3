from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from services.file_store import read_table_file

DATE_COLUMN = "日期"
HOUR_COLUMNS = [f"电价_{i:02d}" for i in range(24)]


def validate_tariff(file_path: Path, strict_tariff: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    df = read_table_file(file_path)

    checks: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}

    missing = [c for c in [DATE_COLUMN, *HOUR_COLUMNS] if c not in df.columns]
    checks.append(
        {
            "name": "电价表字段完整",
            "ok": len(missing) == 0,
            "detail": "字段完整" if not missing else f"缺少列：{', '.join(missing)}",
        }
    )
    if missing:
        return checks, summaries

    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors="coerce")
    date_ok = df[DATE_COLUMN].notna().all()
    checks.append(
        {
            "name": "电价日期可解析",
            "ok": bool(date_ok),
            "detail": "日期列可解析" if date_ok else "存在无法解析日期",
        }
    )

    numeric = df[HOUR_COLUMNS].apply(pd.to_numeric, errors="coerce")
    numeric_ok = numeric.notna().all().all()
    checks.append(
        {
            "name": "电价矩阵为数值",
            "ok": bool(numeric_ok),
            "detail": "24 列电价均为数值" if numeric_ok else "存在缺失或非数值电价",
        }
    )

    row365_ok = len(df) == 365
    checks.append({"name": "电价表 365 天", "ok": row365_ok, "detail": f"当前 {len(df)} 天"})

    duplicate_dates = int(df[DATE_COLUMN].duplicated().sum()) if date_ok else -1
    checks.append(
        {
            "name": "电价日期无重复",
            "ok": duplicate_dates == 0,
            "detail": "日期无重复" if duplicate_dates == 0 else f"重复日期数：{duplicate_dates}",
        }
    )

    if date_ok:
        sorted_dates = df[DATE_COLUMN].sort_values().reset_index(drop=True)
        diffs = sorted_dates.diff().dropna()
        continuous_ok = bool((diffs == pd.Timedelta(days=1)).all()) if not diffs.empty else False
    else:
        continuous_ok = False

    checks.append(
        {
            "name": "电价日期连续",
            "ok": continuous_ok,
            "detail": "日期逐天连续" if continuous_ok else "日期不连续",
        }
    )

    distinct_patterns = int(numeric.drop_duplicates().shape[0]) if numeric_ok else 0

    summaries.update(
        {
            "row_count": int(len(df)),
            "start_date": str(df[DATE_COLUMN].min().date()) if date_ok else None,
            "end_date": str(df[DATE_COLUMN].max().date()) if date_ok else None,
            "min_price": float(numeric.min().min()) if numeric_ok else None,
            "max_price": float(numeric.max().max()) if numeric_ok else None,
            "pattern_count": distinct_patterns,
            "strict_tariff": strict_tariff,
        }
    )

    return checks, summaries