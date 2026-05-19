# -*- coding: utf-8 -*-
"""将工业/商业节点中间 Excel 转换为 runtime CSV 文件。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


MAP_XLSX_NAME = "03_全年逐日模型映射表.xlsx"
LIB_XLSX_NAME = "04_组合典型日负荷模型库.xlsx"

OUT_MAP_CSV_NAME = "runtime_year_model_map.csv"
OUT_LIB_CSV_NAME = "runtime_model_library.csv"


def normalize_external_model_id(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    s = s.replace("（", "(").replace("）", ")").replace("，", ",")
    s = re.sub(r"\s+", "", s)
    m = re.fullmatch(r"\((\d+),(\d+)\)", s)
    if m:
        return f"({int(m.group(1))},{int(m.group(2))})"
    return s


def parse_combo_id_for_sort(combo_id: str) -> Tuple[int, int, str]:
    m = re.fullmatch(r"\((\d+),(\d+)\)", combo_id)
    if m:
        return int(m.group(1)), int(m.group(2)), combo_id
    return 999999, 999999, combo_id


def find_hour_columns(df: pd.DataFrame) -> List[str]:
    hour_cols = []
    for c in df.columns:
        c_str = str(c).strip()
        if re.fullmatch(r"\d{2}:\d{2}", c_str):
            hour_cols.append(c_str)
    hour_cols = sorted(hour_cols, key=lambda x: int(x.split(":")[0]))
    if len(hour_cols) != 24:
        raise ValueError(
            f"模型24点曲线工作表识别到的小时列不是24个，而是 {len(hour_cols)} 个：{hour_cols}"
        )
    expected = [f"{i:02d}:00" for i in range(24)]
    if hour_cols != expected:
        raise ValueError(
            f"小时列不是标准 00:00~23:00 顺序。\n识别到：{hour_cols}\n期望：{expected}"
        )
    return hour_cols


def load_year_model_map(map_xlsx: Path) -> pd.DataFrame:
    df = pd.read_excel(map_xlsx)
    required_cols = ["日期", "组合模型编号", "组合模型名称"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{map_xlsx.name} 缺少必要列：{missing}")
    out = df[required_cols].copy()
    out = out.rename(
        columns={
            "日期": "date",
            "组合模型编号": "external_model_id",
            "组合模型名称": "model_name",
        }
    )
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["external_model_id"] = out["external_model_id"].apply(normalize_external_model_id)
    out["model_name"] = out["model_name"].astype(str).str.strip()
    out = out[out["date"].notna()].copy()
    out = out.sort_values("date").reset_index(drop=True)
    out["day_index"] = range(len(out))
    if out["date"].duplicated().any():
        dup_dates = out.loc[out["date"].duplicated(), "date"].dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"{map_xlsx.name} 存在重复日期：{dup_dates[:10]}")
    if (out["external_model_id"] == "").any():
        bad_rows = out.index[out["external_model_id"] == ""].tolist()
        raise ValueError(f"{map_xlsx.name} 存在空的组合模型编号，行号索引示例：{bad_rows[:10]}")
    if len(out) != 365:
        raise ValueError(f"{map_xlsx.name} 日期行数应为365天，实际为 {len(out)} 行")
    return out


def load_model_library(lib_xlsx: Path) -> pd.DataFrame:
    df = pd.read_excel(lib_xlsx, sheet_name="模型24点曲线")
    required_cols = ["组合模型编号", "组合模型名称"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f'{lib_xlsx.name} 的模型24点曲线缺少必要列：{missing}')
    hour_cols = find_hour_columns(df)
    out = df[required_cols + hour_cols].copy()
    out = out.rename(
        columns={
            "组合模型编号": "external_model_id",
            "组合模型名称": "model_name",
        }
    )
    out["external_model_id"] = out["external_model_id"].apply(normalize_external_model_id)
    out["model_name"] = out["model_name"].astype(str).str.strip()
    out = out[out["external_model_id"] != ""].copy()
    if out["external_model_id"].duplicated().any():
        dup_ids = out.loc[out["external_model_id"].duplicated(), "external_model_id"].tolist()
        raise ValueError(f"{lib_xlsx.name} 的模型库存在重复组合模型编号：{dup_ids}")
    rename_hour_map = {f"{i:02d}:00": f"h{i:02d}" for i in range(24)}
    out = out.rename(columns=rename_hour_map)
    hour_out_cols = [f"h{i:02d}" for i in range(24)]
    for c in hour_out_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if out[hour_out_cols].isna().any().any():
        bad_mask = out[hour_out_cols].isna().any(axis=1)
        bad_ids = out.loc[bad_mask, "external_model_id"].tolist()
        raise ValueError(f"{lib_xlsx.name} 存在无法解析为数值的24点曲线，模型编号：{bad_ids}")
    if (out[hour_out_cols] < 0).any().any():
        bad_mask = (out[hour_out_cols] < 0).any(axis=1)
        bad_ids = out.loc[bad_mask, "external_model_id"].tolist()
        raise ValueError(f"{lib_xlsx.name} 存在负负荷值，模型编号：{bad_ids}")
    return out


def build_internal_model_mapping(
    year_map_df: pd.DataFrame,
    library_df: pd.DataFrame,
) -> Dict[str, int]:
    lib_ids = library_df["external_model_id"].dropna().astype(str).tolist()
    year_ids = year_map_df["external_model_id"].dropna().astype(str).tolist()
    lib_id_set = set(lib_ids)
    year_id_set = set(year_ids)
    missing_in_lib = sorted(year_id_set - lib_id_set, key=parse_combo_id_for_sort)
    if missing_in_lib:
        raise ValueError(
            f"全年逐日映射表中存在模型库没有的组合模型编号：{missing_in_lib}"
        )
    sorted_ids = sorted(lib_id_set, key=parse_combo_id_for_sort)
    return {ext_id: idx for idx, ext_id in enumerate(sorted_ids)}


def build_runtime_year_model_map(
    year_map_df: pd.DataFrame,
    internal_map: Dict[str, int],
) -> pd.DataFrame:
    out = year_map_df.copy()
    out["internal_model_id"] = out["external_model_id"].map(internal_map)
    if out["internal_model_id"].isna().any():
        bad_ids = out.loc[out["internal_model_id"].isna(), "external_model_id"].unique().tolist()
        raise ValueError(f"存在无法映射为内部模型编号的外部模型编号：{bad_ids}")
    out["internal_model_id"] = out["internal_model_id"].astype(int)
    out = out[["date", "day_index", "internal_model_id", "external_model_id", "model_name"]].copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out


def build_runtime_model_library(
    library_df: pd.DataFrame,
    internal_map: Dict[str, int],
) -> pd.DataFrame:
    out = library_df.copy()
    out["internal_model_id"] = out["external_model_id"].map(internal_map)
    if out["internal_model_id"].isna().any():
        bad_ids = out.loc[out["internal_model_id"].isna(), "external_model_id"].unique().tolist()
        raise ValueError(f"模型库中存在无法映射的外部模型编号：{bad_ids}")
    out["internal_model_id"] = out["internal_model_id"].astype(int)
    hour_cols = [f"h{i:02d}" for i in range(24)]
    out = out[["internal_model_id", "external_model_id", "model_name"] + hour_cols].copy()
    out = out.sort_values("internal_model_id").reset_index(drop=True)
    return out


def process_one_node(input_dir: str | Path, output_dir: str | Path) -> dict:
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year_map_df = load_year_model_map(in_dir / MAP_XLSX_NAME)
    library_df = load_model_library(in_dir / LIB_XLSX_NAME)
    internal_map = build_internal_model_mapping(year_map_df, library_df)
    runtime_year_map_df = build_runtime_year_model_map(year_map_df, internal_map)
    runtime_library_df = build_runtime_model_library(library_df, internal_map)
    map_path = out_dir / OUT_MAP_CSV_NAME
    lib_path = out_dir / OUT_LIB_CSV_NAME
    runtime_year_map_df.to_csv(map_path, index=False, encoding="utf-8-sig")
    runtime_library_df.to_csv(lib_path, index=False, encoding="utf-8-sig")
    return {"year_map_path": str(map_path), "model_library_path": str(lib_path)}
