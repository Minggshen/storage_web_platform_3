from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import numpy as np
import pandas as pd


HOUR_COLS = [f"h{i:02d}" for i in range(24)]


def _resolve_runtime_paths(
    scenario: Mapping[str, Any],
    project_root: Path | None = None,
) -> tuple[Path, Path]:
    """
    从节点条目中解析 runtime_year_model_map 与 runtime_model_library 路径。

    允许两种显式写法：
    1. 直接给 year_model_map_path / model_library_path
    2. 给 node_dir + year_model_map_file + model_library_file

    两种方式都属于显式路径配置，不属于负荷 fallback。
    """
    year_model_map_path = scenario.get("year_model_map_path")
    model_library_path = scenario.get("model_library_path")

    if year_model_map_path and model_library_path:
        year_map_path = Path(str(year_model_map_path))
        lib_path = Path(str(model_library_path))
    else:
        node_dir = scenario.get("node_dir")
        year_model_map_file = scenario.get("year_model_map_file")
        model_library_file = scenario.get("model_library_file")

        if not node_dir or not year_model_map_file or not model_library_file:
            raise ValueError(
                "节点条目缺少 runtime 文件定位信息。"
                "需要提供 year_model_map_path/model_library_path，"
                "或 node_dir/year_model_map_file/model_library_file。"
            )

        node_dir_path = Path(str(node_dir))
        if not node_dir_path.is_absolute():
            if project_root is None:
                raise ValueError("node_dir 为相对路径时，必须提供 project_root。")
            node_dir_path = (project_root / node_dir_path).resolve()
        else:
            node_dir_path = node_dir_path.resolve()

        year_map_path = node_dir_path / str(year_model_map_file)
        lib_path = node_dir_path / str(model_library_file)

    year_map_path = year_map_path.resolve()
    lib_path = lib_path.resolve()

    if not year_map_path.exists():
        raise FileNotFoundError(f"找不到 runtime_year_model_map 文件：{year_map_path}")
    if not lib_path.exists():
        raise FileNotFoundError(f"找不到 runtime_model_library 文件：{lib_path}")

    return year_map_path, lib_path


def _load_year_model_map(csv_path: Path, expected_days: int | None = None) -> np.ndarray:
    """
    读取年度模型映射表。

    模板口径要求：
    - 必须包含 internal_model_id
    - 若有 day_index，则应为 0 ~ expected_days-1 的连续整数
    - 若有 date，则可用于排序
    - internal_model_id 必须为非负整数（允许从 0 开始）
    """
    df = pd.read_csv(csv_path)

    if "internal_model_id" not in df.columns:
        raise ValueError(f"{csv_path.name} 缺少必要列：internal_model_id")

    if df.empty:
        raise ValueError(f"{csv_path.name} 为空。")

    if "day_index" in df.columns:
        df["day_index"] = pd.to_numeric(df["day_index"], errors="coerce")
        day_index_series = df["day_index"]

        if day_index_series.isna().any():
            bad_rows = day_index_series[day_index_series.isna()].index.tolist()[:10]
            raise ValueError(
                f"{csv_path.name} 的 day_index 存在非数值或空值，问题行索引示例：{bad_rows}"
            )

        non_integer_mask = (day_index_series % 1) != 0
        if non_integer_mask.any():
            bad_rows = day_index_series[non_integer_mask].index.tolist()[:10]
            raise ValueError(
                f"{csv_path.name} 的 day_index 必须为整数，问题行索引示例：{bad_rows}"
            )

        df["day_index"] = day_index_series.astype(int)
        df = df.sort_values("day_index").reset_index(drop=True)

        sorted_day_index = df["day_index"]
        if sorted_day_index.duplicated().any():
            dup_vals = sorted_day_index[sorted_day_index.duplicated()].tolist()[:10]
            raise ValueError(f"{csv_path.name} 存在重复 day_index：{dup_vals}")

        if expected_days is not None:
            expected_idx = np.arange(expected_days, dtype=int)
            actual_idx = sorted_day_index.to_numpy(dtype=int)
            if actual_idx.size != expected_days:
                raise ValueError(
                    f"{csv_path.name} 天数与期望不一致：实际 {actual_idx.size}，期望 {expected_days}"
                )
            if not np.array_equal(actual_idx, expected_idx):
                raise ValueError(
                    f"{csv_path.name} 的 day_index 必须按 0~{expected_days - 1} 连续排列。"
                )

    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        date_series = df["date"]

        if date_series.isna().any():
            bad_rows = date_series[date_series.isna()].index.tolist()[:10]
            raise ValueError(
                f"{csv_path.name} 的 date 列存在无法解析的值，问题行索引示例：{bad_rows}"
            )

        df = df.sort_values("date").reset_index(drop=True)
        sorted_date = df["date"]

        if sorted_date.duplicated().any():
            dup_vals = sorted_date[sorted_date.duplicated()].dt.strftime("%Y-%m-%d").tolist()[:10]
            raise ValueError(f"{csv_path.name} 存在重复 date：{dup_vals}")

        if expected_days is not None and len(df) != expected_days:
            raise ValueError(
                f"{csv_path.name} 天数与期望不一致：实际 {len(df)}，期望 {expected_days}"
            )

    else:
        if expected_days is not None and len(df) != expected_days:
            raise ValueError(
                f"{csv_path.name} 天数与期望不一致：实际 {len(df)}，期望 {expected_days}"
            )

    internal_model_id_series = pd.to_numeric(df["internal_model_id"], errors="coerce")
    year_model_map = internal_model_id_series.to_numpy(dtype=float)

    if np.isnan(year_model_map).any():
        bad_rows = np.where(np.isnan(year_model_map))[0].tolist()[:10]
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 存在非数值或空值，问题行索引示例：{bad_rows}"
        )

    if np.any(~np.isfinite(year_model_map)):
        bad_rows = np.where(~np.isfinite(year_model_map))[0].tolist()[:10]
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 存在非有限值，问题行索引示例：{bad_rows}"
        )

    non_integer_mask = (year_model_map % 1) != 0
    if np.any(non_integer_mask):
        bad_rows = np.where(non_integer_mask)[0].tolist()[:10]
        bad_vals = year_model_map[non_integer_mask][:10].tolist()
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 必须为整数，"
            f"问题行索引示例：{bad_rows}，问题值示例：{bad_vals}"
        )

    year_model_map = year_model_map.astype(int)

    if year_model_map.size == 0:
        raise ValueError(f"{csv_path.name} 为空。")

    negative_mask = year_model_map < 0
    if np.any(negative_mask):
        bad_rows = np.where(negative_mask)[0].tolist()[:10]
        bad_vals = year_model_map[negative_mask][:10].tolist()
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 必须为非负整数（允许从0开始），"
            f"问题行索引示例：{bad_rows}，问题值示例：{bad_vals}"
        )

    if expected_days is not None and year_model_map.size != expected_days:
        raise ValueError(
            f"{csv_path.name} 天数与期望不一致："
            f"实际 {year_model_map.size}，期望 {expected_days}"
        )

    return year_model_map


def _load_model_library(csv_path: Path) -> Dict[int, np.ndarray]:
    """
    读取典型日模型库。

    模板口径要求：
    - 必须包含 internal_model_id, h00~h23
    - internal_model_id 必须为非负整数（允许从 0 开始）
    - 每个模型必须正好 24 个点，且非负、有限
    """
    df = pd.read_csv(csv_path)

    required_cols = {"internal_model_id", *HOUR_COLS}
    missing = sorted(required_cols - set(df.columns))
    if missing:
        raise ValueError(f"{csv_path.name} 缺少必要列：{missing}")

    if df.empty:
        raise ValueError(f"{csv_path.name} 为空。")

    internal_model_id_series = pd.to_numeric(df["internal_model_id"], errors="coerce")
    if internal_model_id_series.isna().any():
        bad_rows = internal_model_id_series[internal_model_id_series.isna()].index.tolist()[:10]
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 存在非数值或空值，问题行索引示例：{bad_rows}"
        )

    internal_model_id_float = internal_model_id_series.to_numpy(dtype=float)
    finite_mask = np.isfinite(internal_model_id_float)
    if not np.all(finite_mask):
        bad_rows = np.where(~finite_mask)[0].tolist()[:10]
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 存在非有限值，问题行索引示例：{bad_rows}"
        )

    non_integer_mask = (internal_model_id_float % 1) != 0
    if np.any(non_integer_mask):
        bad_rows = np.where(non_integer_mask)[0].tolist()[:10]
        bad_vals = internal_model_id_float[non_integer_mask][:10].tolist()
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 必须为整数，"
            f"问题行索引示例：{bad_rows}，问题值示例：{bad_vals}"
        )

    df["internal_model_id"] = internal_model_id_float.astype(int)
    internal_model_id_int = df["internal_model_id"].to_numpy(dtype=int)

    negative_mask = internal_model_id_int < 0
    if np.any(negative_mask):
        bad_rows = np.where(negative_mask)[0].tolist()[:10]
        bad_vals = internal_model_id_int[negative_mask][:10].tolist()
        raise ValueError(
            f"{csv_path.name} 的 internal_model_id 必须为非负整数（允许从0开始），"
            f"问题行索引示例：{bad_rows}，问题值示例：{bad_vals}"
        )

    duplicated_mask = df["internal_model_id"].duplicated().to_numpy(dtype=bool)
    if np.any(duplicated_mask):
        dup_ids = df["internal_model_id"].to_numpy(dtype=int)[duplicated_mask].tolist()
        raise ValueError(f"{csv_path.name} 存在重复 internal_model_id：{dup_ids}")

    model_library: Dict[int, np.ndarray] = {}

    for _, row in df.iterrows():
        model_id = int(row["internal_model_id"])
        hour_values_series = row.loc[HOUR_COLS]
        values = pd.to_numeric(hour_values_series, errors="coerce").to_numpy(dtype=float)

        if values.size != 24:
            raise ValueError(f"{csv_path.name} 中 model_id={model_id} 的曲线长度不是 24。")
        if np.any(np.isnan(values)):
            raise ValueError(f"{csv_path.name} 中 model_id={model_id} 的曲线存在空值或非数值。")
        if np.any(~np.isfinite(values)):
            raise ValueError(f"{csv_path.name} 中 model_id={model_id} 的曲线存在非有限值。")
        if np.any(values < 0):
            raise ValueError(f"{csv_path.name} 中 model_id={model_id} 的曲线存在负值。")

        model_library[model_id] = values.copy()

    if not model_library:
        raise ValueError(f"{csv_path.name} 中没有可用模型。")

    return model_library


def has_runtime_payload(scenario: Mapping[str, Any]) -> bool:
    if scenario.get("year_model_map_path") and scenario.get("model_library_path"):
        return True

    return bool(
        scenario.get("node_dir")
        and scenario.get("year_model_map_file")
        and scenario.get("model_library_file")
    )


def load_runtime_bundle(
    scenario: Mapping[str, Any],
    project_root: Path | None = None,
    expected_days: int | None = None,
) -> Dict[str, Any]:
    """
    读取单个节点 runtime bundle：
    - year_model_map
    - model_library
    - preview_profile（全年第 1 天对应的典型日曲线）
    - runtime 文件路径
    """
    year_map_path, lib_path = _resolve_runtime_paths(scenario, project_root=project_root)

    year_model_map = _load_year_model_map(year_map_path, expected_days=expected_days)
    model_library = _load_model_library(lib_path)

    used_model_ids = set(np.unique(year_model_map).tolist())
    lib_model_ids = set(model_library.keys())
    missing_in_lib = sorted(used_model_ids - lib_model_ids)
    if missing_in_lib:
        raise ValueError(
            f"{year_map_path.name} 中引用了 {lib_path.name} 中不存在的模型编号：{missing_in_lib}"
        )

    preview_model_id = int(year_model_map[0])
    preview_profile = model_library[preview_model_id].copy()

    return {
        "year_model_map_path": str(year_map_path),
        "model_library_path": str(lib_path),
        "year_model_map": year_model_map.copy(),
        "model_library": {k: v.copy() for k, v in model_library.items()},
        "preview_profile": preview_profile.copy(),
        "preview_model_id": preview_model_id,
    }


def get_day_profile_from_runtime_entry(entry: Mapping[str, Any], day_index: int) -> np.ndarray:
    """
    从单个节点 runtime entry 中读取指定 day_index 的 24 点曲线。
    """
    year_model_map = np.asarray(entry["year_model_map"], dtype=int).reshape(-1)
    if day_index < 0 or day_index >= year_model_map.size:
        raise IndexError(f"day_index 超出范围：{day_index}")

    model_id = int(year_model_map[day_index])
    model_library = entry["model_library"]

    if model_id not in model_library:
        raise KeyError(f"model_id={model_id} 不存在于 model_library 中。")

    profile = np.asarray(model_library[model_id], dtype=float).reshape(-1)
    if profile.size != 24:
        raise ValueError(f"model_id={model_id} 的曲线长度不是 24。")

    return profile.copy()


def load_all_node_runtime_bundles(
    scenarios: Iterable[Mapping[str, Any]],
    project_root: Path | None = None,
    expected_days: int | None = None,
) -> Dict[int, Dict[str, Any]]:
    """
    严格预加载所有节点 runtime 数据。
    当前工程中不允许跳过没有 runtime 的节点。
    """
    db: Dict[int, Dict[str, Any]] = {}

    for scenario in scenarios:
        node_id = int(scenario.get("target_node", scenario.get("node_id", -1)))
        if node_id <= 0:
            raise ValueError(f"存在非法 node_id：{node_id}")

        if not has_runtime_payload(scenario):
            raise ValueError(
                f"node_id={node_id} 缺少 runtime 文件定位信息。"
                "当前工程要求所有启用节点都必须提供 runtime 数据。"
            )

        if node_id in db:
            raise ValueError(f"重复 node_id：{node_id}")

        if "q_to_p_ratio" not in scenario:
            raise ValueError(f"node_id={node_id} 缺少 q_to_p_ratio。当前工程不允许兜底。")

        q_to_p_ratio = float(scenario["q_to_p_ratio"])
        if not np.isfinite(q_to_p_ratio):
            raise ValueError(f"node_id={node_id} 的 q_to_p_ratio 不是有限值。")
        if q_to_p_ratio < 0:
            raise ValueError(f"node_id={node_id} 的 q_to_p_ratio 不能为负。")

        payload = load_runtime_bundle(
            scenario=scenario,
            project_root=project_root,
            expected_days=expected_days,
        )

        db[node_id] = {
            "node_id": node_id,
            "name": str(scenario.get("name", "")),
            "category": str(scenario.get("category", "")),
            "q_to_p_ratio": q_to_p_ratio,
            "year_model_map_path": payload["year_model_map_path"],
            "model_library_path": payload["model_library_path"],
            "year_model_map": payload["year_model_map"].copy(),
            "model_library": {k: v.copy() for k, v in payload["model_library"].items()},
            "preview_profile": payload["preview_profile"].copy(),
            "preview_model_id": int(payload["preview_model_id"]),
        }

    return db