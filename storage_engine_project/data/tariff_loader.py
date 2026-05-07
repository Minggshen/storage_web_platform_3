from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from storage_engine_project.config.tariff_config import TariffConfig


def _detect_hourly_price_columns(cfg: TariffConfig, df: pd.DataFrame) -> List[str]:
    """
    严格识别 24 个逐时电价列。
    当前唯一允许格式：电价_00 ~ 电价_23
    """
    expected_cols = list(cfg.schema.hourly_price_columns)
    missing = [col for col in expected_cols if col not in df.columns]
    if missing:
        raise ValueError(f"电价文件缺少逐时电价列：{missing}")
    return expected_cols


def _validate_daily_hourly_tariff_table(
    out: pd.DataFrame,
    cfg: TariffConfig,
    file_path: Path,
    hour_cols: List[str],
) -> None:
    """
    严格校验逐日逐时电价表：
    1. 日期可解析
    2. 日期唯一且连续
    3. 天数严格等于 days_per_year
    4. 24 列小时电价均为非负有限数值
    """
    if out.empty:
        raise ValueError(f"电价文件为空：{file_path}")

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if out["date"].isna().any():
        bad_rows = out.index[out["date"].isna()].tolist()[:10]
        raise ValueError(
            f"{file_path.name} 的日期列存在无法解析的值，异常行索引示例：{bad_rows}"
        )

    out.sort_values("date", inplace=True)
    out.reset_index(drop=True, inplace=True)

    if out["date"].duplicated().any():
        dup_dates = (
            out.loc[out["date"].duplicated(), "date"]
            .dt.strftime("%Y-%m-%d")
            .tolist()[:10]
        )
        raise ValueError(f"{file_path.name} 存在重复日期：{dup_dates}")

    for col in hour_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    if out[hour_cols].isna().any().any():
        raise ValueError(f"{file_path.name} 的逐时电价列存在空值或非数值。")

    matrix = out[hour_cols].to_numpy(dtype=float)
    if np.any(~np.isfinite(matrix)):
        raise ValueError(f"{file_path.name} 的逐时电价列存在非有限值。")

    if (matrix < 0).any():
        raise ValueError(f"{file_path.name} 的逐时电价列存在负值。")

    if len(out) != int(cfg.days_per_year):
        raise ValueError(
            f"{file_path.name} 的日数与配置不一致：实际 {len(out)} 天，"
            f"期望 {cfg.days_per_year} 天。"
        )

    if int(cfg.hours_per_day) != 24:
        raise ValueError("当前工程仅支持 24 点小时级电价。")

    start_date = out["date"].iloc[0]
    expected_dates = pd.date_range(
        start=start_date,
        periods=int(cfg.days_per_year),
        freq="D",
    )

    actual_dates = pd.DatetimeIndex(out["date"].to_numpy())

    if not actual_dates.equals(expected_dates):
        missing_dates = expected_dates.difference(actual_dates)
        extra_dates = actual_dates.difference(expected_dates)

        msg_parts = [
            f"{file_path.name} 的日期不是连续自然日序列。",
            f"起始日期为 {start_date.date()}。"
        ]

        if len(missing_dates) > 0:
            msg_parts.append(
                "缺失日期示例："
                + ", ".join(d.strftime("%Y-%m-%d") for d in missing_dates[:10])
            )

        if len(extra_dates) > 0:
            msg_parts.append(
                "异常日期示例："
                + ", ".join(d.strftime("%Y-%m-%d") for d in extra_dates[:10])
            )

        raise ValueError(" ".join(msg_parts))


def _build_tariff_list_and_period_index(
    price_year_matrix: np.ndarray,
) -> tuple[list[Dict[str, Any]], np.ndarray]:
    """
    将全年逐日逐时电价矩阵按“唯一日型电价向量”聚合，
    生成 tariff_list 与 year_period_index。
    这两者都是从电价表推导出的派生结果，不是默认电价。
    """
    days_per_year = int(price_year_matrix.shape[0])

    tariff_list: list[Dict[str, Any]] = []
    vector_to_period_idx: dict[tuple, int] = {}
    year_period_index = np.zeros(days_per_year, dtype=int)

    for day_idx in range(days_per_year):
        vec = np.asarray(price_year_matrix[day_idx, :], dtype=float).reshape(-1)
        key = tuple(np.round(vec, 10).tolist())

        if key not in vector_to_period_idx:
            period_idx = len(tariff_list)
            vector_to_period_idx[key] = period_idx
            tariff_list.append(
                {
                    "name": f"日型电价{period_idx + 1}",
                    "days": 1,
                    "price_vector": vec.copy(),
                }
            )
        else:
            period_idx = vector_to_period_idx[key]
            tariff_list[period_idx]["days"] += 1

        year_period_index[day_idx] = period_idx

    return tariff_list, year_period_index


def parse_tariff_excel(
    file_path: str | Path,
    cfg: TariffConfig,
) -> Dict[str, Any]:
    """
    严格解析唯一允许的电价格式：
    - 日期
    - 电价_00 ~ 电价_23
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"电价文件不存在：{path}")

    df = pd.read_excel(path)
    if df.empty:
        raise ValueError(f"电价文件为空：{path}")

    date_col = cfg.schema.date_col
    if date_col not in df.columns:
        raise ValueError(
            f"电价文件缺少日期列：{date_col}。"
            "当前工程只允许“日期 + 电价_00~电价_23”格式。"
        )

    hour_cols = _detect_hourly_price_columns(cfg, df)

    out = df[[date_col] + hour_cols].copy()
    out = out.rename(columns={date_col: "date"})

    _validate_daily_hourly_tariff_table(
        out=out,
        cfg=cfg,
        file_path=path,
        hour_cols=hour_cols,
    )

    price_year_matrix = out[hour_cols].to_numpy(dtype=float)
    expected_shape = (int(cfg.days_per_year), int(cfg.hours_per_day))
    if price_year_matrix.shape != expected_shape:
        raise ValueError(
            f"{path.name} 生成的 price_year_matrix 形状异常："
            f"实际 {price_year_matrix.shape}，期望 {expected_shape}"
        )

    tariff_list, year_period_index = _build_tariff_list_and_period_index(
        price_year_matrix=price_year_matrix
    )

    if not tariff_list:
        raise ValueError(f"{path.name} 未解析出任何有效日电价类型。")

    return {
        "tariff_list": tariff_list,
        "price_year_matrix": price_year_matrix.copy(),
        "price_year": price_year_matrix.copy(),
        "year_period_index": year_period_index.copy(),
        "price_e": price_year_matrix[0, :].copy(),
        "tariff_source": str(path.resolve()),
        "fallback_used": False,
        "tariff_format": "daily_hourly_matrix_strict",
    }


def build_default_tariff_payload(cfg: TariffConfig) -> Dict[str, Any]:
    """
    严格模式下禁止构造默认电价。
    """
    _ = cfg
    raise RuntimeError(
        "当前工程已禁用默认电价 fallback。"
        "必须从唯一指定的逐日逐时电价 Excel 成功读取全年电价数据。"
    )


def load_tariff_data(
    tariff_config: TariffConfig,
    project_root: Path | None = None,
) -> Dict[str, Any]:
    """
    加载分时电价数据。

    严格逻辑：
    1. 只读取 tariff_config.excel_path 指定的唯一文件
    2. 不存在候选顺序
    3. 不允许 fallback
    4. 读取失败直接报错
    """
    file_path = tariff_config.resolve_excel_path(project_root)
    return parse_tariff_excel(file_path, tariff_config)