from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from services.file_store import normalize_column_name, read_table_file

REGISTRY_REQUIRED_COLUMNS = [
    "enabled",
    "optimize_storage",
    "node_id",
    "scenario_name",
    "category",
    "node_dir",
    "year_model_map_file",
    "model_library_file",
    "pv_capacity_kw",
    "q_to_p_ratio",
    "transformer_capacity_kva",
    "transformer_pf_limit",
    "transformer_reserve_ratio",
    "grid_interconnection_limit_kw",
    "device_power_max_kw",
    "search_power_min_kw",
    "search_duration_min_h",
    "search_duration_max_h",
    "dispatch_mode",
    "voltage_penalty_coeff_yuan",
    "run_mode",
]

VALID_CATEGORIES = {"industrial", "commercial", "residential"}
VALID_DISPATCH_MODES = {"tou_greedy", "lp_daily", "daily_lp", "rule_based", "none", "hybrid"}
VALID_RUN_MODES = {"single_user", "multi_user", "template_only"}


def _load_registry_dataframe(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(file_path)
        df.columns = [normalize_column_name(c) for c in df.columns]
        return df

    raw = read_table_file(file_path, sheet_name="node_registry", header=None)

    header_row = None
    for idx in range(min(len(raw), 8)):
        values = {normalize_column_name(v) for v in raw.iloc[idx].tolist()}
        if {"enabled", "node_id", "scenario_name"}.issubset(values):
            header_row = idx
            break

    if header_row is None:
        raise ValueError("无法识别 node_registry 表头行，期望包含 enabled、node_id、scenario_name。")

    headers = [normalize_column_name(v) for v in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 1 :].copy()
    df.columns = headers
    df = df.dropna(how="all").reset_index(drop=True)
    return df


def validate_registry(file_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    df = _load_registry_dataframe(file_path)

    checks: List[Dict[str, Any]] = []
    summaries: Dict[str, Any] = {}

    missing = [col for col in REGISTRY_REQUIRED_COLUMNS if col not in df.columns]
    checks.append(
        {
            "name": "注册表必需列",
            "ok": len(missing) == 0,
            "detail": "必需列完整" if not missing else f"缺少列：{', '.join(missing)}",
        }
    )
    if missing:
        return checks, summaries

    numeric_cols = [
        "enabled",
        "optimize_storage",
        "node_id",
        "pv_capacity_kw",
        "q_to_p_ratio",
        "transformer_capacity_kva",
        "transformer_pf_limit",
        "transformer_reserve_ratio",
        "grid_interconnection_limit_kw",
        "device_power_max_kw",
        "search_power_min_kw",
        "search_duration_min_h",
        "search_duration_max_h",
        "voltage_penalty_coeff_yuan",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    enabled_ok = df["enabled"].dropna().isin([0, 1]).all()
    optimize_ok = df["optimize_storage"].dropna().isin([0, 1]).all()
    checks.append(
        {
            "name": "启用/优化开关合法性",
            "ok": bool(enabled_ok and optimize_ok),
            "detail": "enabled 与 optimize_storage 均为 0/1"
            if enabled_ok and optimize_ok
            else "enabled 或 optimize_storage 存在非 0/1 值",
        }
    )

    duplicate_node_ids = df.loc[df["node_id"].duplicated(), "node_id"].tolist()
    checks.append(
        {
            "name": "node_id 唯一性",
            "ok": len(duplicate_node_ids) == 0,
            "detail": "node_id 无重复" if not duplicate_node_ids else f"重复 node_id：{duplicate_node_ids}",
        }
    )

    category_ok = df["category"].astype(str).str.strip().isin(VALID_CATEGORIES).all()
    bad_categories = sorted(
        set(df.loc[~df["category"].astype(str).str.strip().isin(VALID_CATEGORIES), "category"].astype(str))
    )
    checks.append(
        {
            "name": "category 合法性",
            "ok": bool(category_ok),
            "detail": "category 合法" if category_ok else f"非法 category：{bad_categories}",
        }
    )

    positive_node_id_ok = (df["node_id"] > 0).all()
    checks.append(
        {
            "name": "node_id 正整数",
            "ok": bool(positive_node_id_ok),
            "detail": "node_id 全部大于 0" if positive_node_id_ok else "存在非正 node_id",
        }
    )

    # 只对“启用且参与优化”的节点检查搜索边界和变压器参数
    optimize_df = df[(df["enabled"] == 1) & (df["optimize_storage"] == 1)].copy()

    if optimize_df.empty:
        checks.append(
            {
                "name": "搜索边界范围",
                "ok": True,
                "detail": "当前无参与优化节点，跳过搜索边界检查",
            }
        )
        checks.append(
            {
                "name": "变压器参数范围",
                "ok": True,
                "detail": "当前无参与优化节点，跳过变压器参数检查",
            }
        )
    else:
        power_bounds = optimize_df[["search_power_min_kw", "device_power_max_kw"]].dropna(how="any")
        duration_bounds = optimize_df[["search_duration_min_h", "search_duration_max_h"]].dropna(how="any")
        power_ok = True if power_bounds.empty else (power_bounds["search_power_min_kw"] <= power_bounds["device_power_max_kw"]).all()
        duration_ok = True if duration_bounds.empty else (duration_bounds["search_duration_min_h"] <= duration_bounds["search_duration_max_h"]).all()
        search_range_ok = bool(power_ok and duration_ok)
        search_range_detail = (
            "未显式填写搜索边界，将由求解器根据负荷特性和变压器容量自动推断"
            if power_bounds.empty and duration_bounds.empty
            else "功率/时长边界合理"
        )
        checks.append(
            {
                "name": "搜索边界范围",
                "ok": search_range_ok,
                "detail": search_range_detail if search_range_ok else "存在最小值大于最大值的情况",
            }
        )

        transformer_ok = bool(
            (optimize_df["transformer_capacity_kva"] > 0).all()
            and optimize_df["transformer_pf_limit"].between(0, 1).all()
            and optimize_df["transformer_reserve_ratio"].between(0, 1).all()
        )
        checks.append(
            {
                "name": "变压器参数范围",
                "ok": transformer_ok,
                "detail": "变压器参数范围正常" if transformer_ok else "变压器参数存在异常值",
            }
        )

    dispatch_values = set(df["dispatch_mode"].astype(str).str.strip())
    dispatch_ok = dispatch_values.issubset(VALID_DISPATCH_MODES)
    checks.append(
        {
            "name": "dispatch_mode 合法性",
            "ok": dispatch_ok,
            "detail": "dispatch_mode 合法"
            if dispatch_ok
            else f"发现未知 dispatch_mode：{sorted(dispatch_values - VALID_DISPATCH_MODES)}",
        }
    )

    run_values = set(df["run_mode"].astype(str).str.strip())
    run_ok = run_values.issubset(VALID_RUN_MODES)
    checks.append(
        {
            "name": "run_mode 合法性",
            "ok": run_ok,
            "detail": "run_mode 合法" if run_ok else f"发现未知 run_mode：{sorted(run_values - VALID_RUN_MODES)}",
        }
    )

    summaries.update(
        {
            "row_count": int(len(df)),
            "enabled_count": int(df["enabled"].sum()),
            "optimize_storage_count": int(df["optimize_storage"].sum()),
            "optimize_target_count": int(len(optimize_df)),
            "category_counts": {k: int(v) for k, v in df["category"].value_counts().to_dict().items()},
            "max_node_id": int(df["node_id"].max()),
            "columns": list(df.columns),
        }
    )

    return checks, summaries
