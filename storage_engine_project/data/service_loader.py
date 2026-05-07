from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from storage_engine_project.config.service_config import ServiceConfig


@dataclass(slots=True)
class ServiceCalendar:
    """
    年度服务场景对象。
    后续第二层将根据 availability / 价格 / activation_factor 计算服务收益。
    """

    scenario_name: str
    availability_matrix: np.ndarray                    # 365x24, 0/1 或 [0,1]
    capacity_price_matrix_yuan_per_kw: np.ndarray      # 365x24
    delivery_price_matrix_yuan_per_kwh: np.ndarray     # 365x24
    penalty_price_matrix_yuan_per_kwh: np.ndarray      # 365x24
    activation_factor_matrix: np.ndarray               # 365x24

    def __post_init__(self) -> None:
        for name in [
            "availability_matrix",
            "capacity_price_matrix_yuan_per_kw",
            "delivery_price_matrix_yuan_per_kwh",
            "penalty_price_matrix_yuan_per_kwh",
            "activation_factor_matrix",
        ]:
            value = getattr(self, name)
            arr = np.asarray(value, dtype=float)
            if arr.shape != (365, 24):
                raise ValueError(f"{name} 形状必须是 (365, 24)，当前为 {arr.shape}")
            setattr(self, name, arr)


def _read_table(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"服务日历文件不存在：{path}")

    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"暂不支持的文件类型：{path.suffix}")


def _find_hour_columns(df: pd.DataFrame, prefixes: list[str]) -> list[str]:
    matched: list[tuple[int, str]] = []
    lower_map = {str(c).lower(): c for c in df.columns}

    for prefix in prefixes:
        for h in range(24):
            candidates = [
                f"{prefix}{h:02d}",
                f"{prefix}{h}",
                f"{prefix}{h:02d}:00",
                f"{prefix}{h}:00",
            ]
            found = None
            for cand in candidates:
                if cand.lower() in lower_map:
                    found = lower_map[cand.lower()]
                    break
            if found is not None:
                matched.append((h, found))

    if len({h for h, _ in matched}) < 24:
        return []

    matched = sorted({h: col for h, col in matched}.items(), key=lambda x: x[0])
    return [col for _, col in matched]


def _extract_24h_matrix(
    df: pd.DataFrame,
    prefixes: list[str],
    scalar_aliases: list[str],
    default_value: float,
) -> np.ndarray:
    cols = _find_hour_columns(df, prefixes)
    if cols:
        return df[cols].astype(float).to_numpy()

    lower_map = {str(c).lower(): c for c in df.columns}
    for alias in scalar_aliases:
        key = alias.lower()
        if key in lower_map:
            series = df[lower_map[key]].astype(float).to_numpy()
            return np.repeat(series[:, None], 24, axis=1)

    return np.full((len(df), 24), float(default_value), dtype=float)


def build_default_service_calendar(
    config: ServiceConfig,
) -> ServiceCalendar:
    availability = np.zeros((365, 24), dtype=float)
    if config.enable_service:
        for h in config.default_available_hours:
            if 0 <= h <= 23:
                availability[:, h] = 1.0

    capacity = np.full((365, 24), config.default_capacity_price_yuan_per_kw, dtype=float)
    delivery = np.full((365, 24), config.default_delivery_price_yuan_per_kwh, dtype=float)
    penalty = np.full((365, 24), config.default_penalty_price_yuan_per_kwh, dtype=float)
    activation = np.full((365, 24), config.default_activation_factor, dtype=float)

    if not config.enable_service:
        capacity[:, :] = 0.0
        delivery[:, :] = 0.0
        penalty[:, :] = 0.0
        activation[:, :] = 0.0

    return ServiceCalendar(
        scenario_name=config.scenario_name,
        availability_matrix=availability,
        capacity_price_matrix_yuan_per_kw=capacity,
        delivery_price_matrix_yuan_per_kwh=delivery,
        penalty_price_matrix_yuan_per_kwh=penalty,
        activation_factor_matrix=activation,
    )


def load_service_calendar(
    config: ServiceConfig,
    file_path: str | Path | None = None,
) -> ServiceCalendar:
    if not file_path:
        return build_default_service_calendar(config)

    path = Path(file_path)
    if not path.exists():
        return build_default_service_calendar(config)

    df = _read_table(path)
    if df.empty:
        return build_default_service_calendar(config)

    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期").reset_index(drop=True)
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

    if len(df) != 365:
        raise ValueError(
            f"服务日历文件应包含 365 行，当前为 {len(df)} 行：{path}"
        )

    availability = _extract_24h_matrix(
        df,
        prefixes=["服务可用_", "service_available_", "available_", "可参与_"],
        scalar_aliases=["服务可用", "service_available", "available"],
        default_value=1.0 if config.enable_service else 0.0,
    )
    capacity = _extract_24h_matrix(
        df,
        prefixes=["容量价格_", "capacity_price_", "服务容量价格_"],
        scalar_aliases=["容量价格", "capacity_price"],
        default_value=config.default_capacity_price_yuan_per_kw,
    )
    delivery = _extract_24h_matrix(
        df,
        prefixes=["兑现价格_", "delivery_price_", "服务电量价格_"],
        scalar_aliases=["兑现价格", "delivery_price"],
        default_value=config.default_delivery_price_yuan_per_kwh,
    )
    penalty = _extract_24h_matrix(
        df,
        prefixes=["惩罚价格_", "penalty_price_", "违约价格_"],
        scalar_aliases=["惩罚价格", "penalty_price"],
        default_value=config.default_penalty_price_yuan_per_kwh,
    )
    activation = _extract_24h_matrix(
        df,
        prefixes=["激活系数_", "activation_factor_", "服务激活系数_"],
        scalar_aliases=["激活系数", "activation_factor"],
        default_value=config.default_activation_factor,
    )

    if not config.enable_service:
        availability[:, :] = 0.0
        capacity[:, :] = 0.0
        delivery[:, :] = 0.0
        penalty[:, :] = 0.0
        activation[:, :] = 0.0

    return ServiceCalendar(
        scenario_name=config.scenario_name,
        availability_matrix=availability,
        capacity_price_matrix_yuan_per_kw=capacity,
        delivery_price_matrix_yuan_per_kwh=delivery,
        penalty_price_matrix_yuan_per_kwh=penalty,
        activation_factor_matrix=activation,
    )