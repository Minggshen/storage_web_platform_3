# -*- coding: utf-8 -*-
"""
批量将工业/商业节点原始模型文件转换为运行时文件：
1) runtime_year_model_map.csv
2) runtime_model_library.csv

适用目录结构示例：
inputs/
└─ node_loads/
   └─ industrial/
      ├─ node01_工业1/
      │  ├─ 03_全年逐日模型映射表.xlsx
      │  └─ 04_组合典型日负荷模型库.xlsx
      ├─ node02_工业2/
      │  ├─ 03_全年逐日模型映射表.xlsx
      │  └─ 04_组合典型日负荷模型库.xlsx
      └─ ...

说明：
- 这份脚本同样适用于“商业”节点，只要文件格式与工业相同。
- 输出文件将直接写入各节点目录中。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd



ROOT_DIR = Path(
    r"C:\Users\CQU\Desktop\基于配电网末端能效提升的构网型储能方案研究\Python\基于chatgpt5.4thinking模型的负荷配储经济性优化20260310\inputs\node_loads\commercial"
)

MAP_XLSX_NAME = "03_全年逐日模型映射表.xlsx"
LIB_XLSX_NAME = "04_组合典型日负荷模型库.xlsx"

OUT_MAP_CSV_NAME = "runtime_year_model_map.csv"
OUT_LIB_CSV_NAME = "runtime_model_library.csv"


# =========================
# 固定文件名
# =========================
MAP_XLSX_NAME = "03_全年逐日模型映射表.xlsx"
LIB_XLSX_NAME = "04_组合典型日负荷模型库.xlsx"

OUT_MAP_CSV_NAME = "runtime_year_model_map.csv"
OUT_LIB_CSV_NAME = "runtime_model_library.csv"


def normalize_external_model_id(value) -> str:
    """
    规范化外部模型编号，例如：
    '(3,1)' -> '(3,1)'
    '（3，1）' -> '(3,1)'
    ' ( 3 , 1 ) ' -> '(3,1)'
    """
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
    """
    用于排序组合模型编号：
    '(1,2)' -> (1, 2, '(1,2)')
    不能解析的放后面。
    """
    m = re.fullmatch(r"\((\d+),(\d+)\)", combo_id)
    if m:
        return int(m.group(1)), int(m.group(2)), combo_id
    return 999999, 999999, combo_id


def find_hour_columns(df: pd.DataFrame) -> List[str]:
    """
    从模型库中识别 24 个小时列，按 00:00 -> 23:00 排序。
    """
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
    """
    读取 03_全年逐日模型映射表.xlsx
    输出标准字段：
    date, external_model_id, model_name
    """
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

    # 去除空行
    out = out[out["date"].notna()].copy()

    # 排序并重建 day_index
    out = out.sort_values("date").reset_index(drop=True)
    out["day_index"] = range(len(out))

    # 基本校验
    if out["date"].duplicated().any():
        dup_dates = out.loc[out["date"].duplicated(), "date"].dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"{map_xlsx.name} 存在重复日期：{dup_dates[:10]}")

    if (out["external_model_id"] == "").any():
        bad_rows = out.index[out["external_model_id"] == ""].tolist()
        raise ValueError(f"{map_xlsx.name} 存在空的组合模型编号，行号索引示例：{bad_rows[:10]}")

    # 一般应为 365 天；若你以后有闰年数据，这里可改成 len(out) in [365, 366]
    if len(out) != 365:
        raise ValueError(f"{map_xlsx.name} 日期行数应为365天，实际为 {len(out)} 行")

    return out


def load_model_library(lib_xlsx: Path) -> pd.DataFrame:
    """
    读取 04_组合典型日负荷模型库.xlsx 中的“模型24点曲线”工作表
    输出标准字段：
    external_model_id, model_name, h00~h23
    """
    df = pd.read_excel(lib_xlsx, sheet_name="模型24点曲线")

    required_cols = ["组合模型编号", "组合模型名称"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{lib_xlsx.name} 的“模型24点曲线”缺少必要列：{missing}")

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

    # 去空行
    out = out[out["external_model_id"] != ""].copy()

    # 校验唯一性
    if out["external_model_id"].duplicated().any():
        dup_ids = out.loc[out["external_model_id"].duplicated(), "external_model_id"].tolist()
        raise ValueError(f"{lib_xlsx.name} 的模型库存在重复组合模型编号：{dup_ids}")

    # 重命名小时列
    rename_hour_map = {f"{i:02d}:00": f"h{i:02d}" for i in range(24)}
    out = out.rename(columns=rename_hour_map)

    # 数值化校验
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
    为外部模型编号分配内部整数编号。
    策略：
    1) 以模型库中的模型编号为主
    2) 按 (a,b) 自然顺序排序后，映射为 0,1,2,...
    """
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

    # 输出字段顺序
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

    # 再做一次一致性检查
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
    if not ROOT_DIR.exists():
        raise FileNotFoundError(f"根目录不存在：{ROOT_DIR}")

    # 遍历 ROOT_DIR 下所有一级子目录
    node_dirs = [p for p in ROOT_DIR.iterdir() if p.is_dir()]

    if not node_dirs:
        print(f"未在 {ROOT_DIR} 下找到任何节点目录。")
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
        input_dir: 包含 03_全年逐日模型映射表.xlsx / 04_组合典型日负荷模型库.xlsx 的目录
        output_dir: runtime CSV 输出目录
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