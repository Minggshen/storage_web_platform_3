# -*- coding: utf-8 -*-
"""
批量将居民节点原始模型文件转换为运行时文件：
1) runtime_year_model_map.csv
2) runtime_model_library.csv

适用目录结构示例：
inputs/
└─ node_loads/
   └─ residential/
      ├─ node21_居民1/
      │  ├─ 01_全年逐日模型映射表.xlsx
      │  ├─ 02_居民典型日模型库.xlsx
      │  └─ 03_聚类评估结果.xlsx
      ├─ node22_居民2/
      └─ ...

输出文件将直接写入各节点目录中。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


# =========================================================
# 路径设置
# =========================================================
# 推荐写法：脚本放在 project_root/scripts/ 下
PROJECT_ROOT = Path(__file__).resolve().parent.parent
#ROOT_DIR = PROJECT_ROOT / "inputs" / "node_loads" / "residential"

# 如果上面自动定位仍有问题，就改成绝对路径，例如：
ROOT_DIR = Path(
     r"C:\Users\CQU\Desktop\基于配电网末端能效提升的构网型储能方案研究\Python\基于chatgpt5.4thinking模型的负荷配储经济性优化20260310\inputs\node_loads\residential"
)


# =========================================================
# 固定文件名
# =========================================================
MAP_XLSX_NAME = "01_全年逐日模型映射表.xlsx"
LIB_XLSX_NAME = "02_居民典型日模型库.xlsx"

OUT_MAP_CSV_NAME = "runtime_year_model_map.csv"
OUT_LIB_CSV_NAME = "runtime_model_library.csv"


def normalize_model_id(value) -> str:
    """
    规范化居民模型编号：
    'r01' -> 'R01'
    ' R02 ' -> 'R02'
    """
    if pd.isna(value):
        return ""
    s = str(value).strip().upper()
    s = re.sub(r"\s+", "", s)
    return s


def parse_residential_model_id(model_id: str) -> Tuple[int, str]:
    """
    用于排序：
    R01 -> (1, 'R01')
    R12 -> (12, 'R12')
    不能解析的放后面
    """
    m = re.fullmatch(r"R(\d+)", model_id)
    if m:
        return int(m.group(1)), model_id
    return 999999, model_id


def find_hour_columns(df: pd.DataFrame) -> List[str]:
    """
    识别 24 个小时列，要求为 00:00 ~ 23:00
    """
    hour_cols = []
    for c in df.columns:
        c_str = str(c).strip()
        if re.fullmatch(r"\d{2}:\d{2}", c_str):
            hour_cols.append(c_str)

    hour_cols = sorted(hour_cols, key=lambda x: int(x.split(":")[0]))

    if len(hour_cols) != 24:
        raise ValueError(
            f"模型曲线工作表识别到的小时列不是24个，而是 {len(hour_cols)} 个：{hour_cols}"
        )

    expected = [f"{i:02d}:00" for i in range(24)]
    if hour_cols != expected:
        raise ValueError(
            f"小时列不是标准 00:00~23:00 顺序。\n识别到：{hour_cols}\n期望：{expected}"
        )

    return hour_cols


def load_year_model_map(map_xlsx: Path) -> pd.DataFrame:
    """
    读取 01_全年逐日模型映射表.xlsx 的“逐日映射”工作表
    输出标准字段：
    date, external_model_id, model_name
    """
    df = pd.read_excel(map_xlsx, sheet_name="逐日映射")

    required_cols = ["日期", "模型编号", "模型名称"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{map_xlsx.name} 的“逐日映射”缺少必要列：{missing}")

    out = df[required_cols].copy()
    out = out.rename(
        columns={
            "日期": "date",
            "模型编号": "external_model_id",
            "模型名称": "model_name",
        }
    )

    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["external_model_id"] = out["external_model_id"].apply(normalize_model_id)
    out["model_name"] = out["model_name"].astype(str).str.strip()

    out = out[out["date"].notna()].copy()
    out = out.sort_values("date").reset_index(drop=True)
    out["day_index"] = range(len(out))

    if out["date"].duplicated().any():
        dup_dates = out.loc[out["date"].duplicated(), "date"].dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"{map_xlsx.name} 存在重复日期：{dup_dates[:10]}")

    if (out["external_model_id"] == "").any():
        bad_rows = out.index[out["external_model_id"] == ""].tolist()
        raise ValueError(f"{map_xlsx.name} 存在空的模型编号，行索引示例：{bad_rows[:10]}")

    if len(out) != 365:
        raise ValueError(f"{map_xlsx.name} 日期行数应为365天，实际为 {len(out)} 行")

    return out


def load_model_library(lib_xlsx: Path) -> pd.DataFrame:
    """
    读取 02_居民典型日模型库.xlsx 的“模型曲线”工作表
    输出标准字段：
    external_model_id, model_name, h00~h23
    """
    df = pd.read_excel(lib_xlsx, sheet_name="模型曲线")

    required_cols = ["模型编号", "模型名称"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{lib_xlsx.name} 的“模型曲线”缺少必要列：{missing}")

    hour_cols = find_hour_columns(df)

    out = df[required_cols + hour_cols].copy()
    out = out.rename(
        columns={
            "模型编号": "external_model_id",
            "模型名称": "model_name",
        }
    )

    out["external_model_id"] = out["external_model_id"].apply(normalize_model_id)
    out["model_name"] = out["model_name"].astype(str).str.strip()
    out = out[out["external_model_id"] != ""].copy()

    if out["external_model_id"].duplicated().any():
        dup_ids = out.loc[out["external_model_id"].duplicated(), "external_model_id"].tolist()
        raise ValueError(f"{lib_xlsx.name} 的模型库存在重复模型编号：{dup_ids}")

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
    """
    为外部模型编号分配内部整数编号
    例如：
    R01 -> 0
    R02 -> 1
    """
    lib_ids = library_df["external_model_id"].dropna().astype(str).tolist()
    year_ids = year_map_df["external_model_id"].dropna().astype(str).tolist()

    lib_id_set = set(lib_ids)
    year_id_set = set(year_ids)

    missing_in_lib = sorted(year_id_set - lib_id_set, key=parse_residential_model_id)
    if missing_in_lib:
        raise ValueError(f"全年逐日映射表中存在模型库没有的模型编号：{missing_in_lib}")

    sorted_ids = sorted(lib_id_set, key=parse_residential_model_id)
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


def process_one_node_dir(node_dir: Path) -> None:
    map_xlsx = node_dir / MAP_XLSX_NAME
    lib_xlsx = node_dir / LIB_XLSX_NAME

    if not map_xlsx.exists() or not lib_xlsx.exists():
        print(f"[跳过] {node_dir} 缺少必要文件")
        return

    print(f"[处理] {node_dir}")

    year_map_df = load_year_model_map(map_xlsx)
    library_df = load_model_library(lib_xlsx)
    internal_map = build_internal_model_mapping(year_map_df, library_df)

    runtime_year_map_df = build_runtime_year_model_map(year_map_df, internal_map)
    runtime_library_df = build_runtime_model_library(library_df, internal_map)

    used_ids = set(runtime_year_map_df["internal_model_id"].unique().tolist())
    lib_ids = set(runtime_library_df["internal_model_id"].unique().tolist())
    if not used_ids.issubset(lib_ids):
        raise ValueError(f"{node_dir.name} 中逐日映射引用了模型库中不存在的内部模型编号")

    runtime_year_map_path = node_dir / OUT_MAP_CSV_NAME
    runtime_library_path = node_dir / OUT_LIB_CSV_NAME

    runtime_year_map_df.to_csv(runtime_year_map_path, index=False, encoding="utf-8-sig")
    runtime_library_df.to_csv(runtime_library_path, index=False, encoding="utf-8-sig")

    print(f"  已生成: {runtime_year_map_path.name}")
    print(f"  已生成: {runtime_library_path.name}")


def main():
    print("ROOT_DIR =", ROOT_DIR)
    print("ROOT_DIR.exists() =", ROOT_DIR.exists())

    if not ROOT_DIR.exists():
        raise FileNotFoundError(f"根目录不存在：{ROOT_DIR}")

    node_dirs = [p for p in ROOT_DIR.iterdir() if p.is_dir()]
    if not node_dirs:
        print(f"未在 {ROOT_DIR} 下找到任何居民节点目录。")
        return

    for node_dir in sorted(node_dirs):
        try:
            process_one_node_dir(node_dir)
        except Exception as e:
            print(f"[失败] {node_dir.name} -> {e}")

    print("\n全部处理完成。")


if __name__ == "__main__":
    main()


def process_one_node(input_dir: str | Path, output_dir: str | Path) -> dict:
    """
    供后端调用：从中间 Excel 生成 runtime CSV。

    Args:
        input_dir: 包含 01_全年逐日模型映射表.xlsx / 02_居民典型日模型库.xlsx 的目录
        output_dir: runtime CSV 输出目录

    Returns:
        {"year_map_path": str, "model_library_path": str}
    """
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