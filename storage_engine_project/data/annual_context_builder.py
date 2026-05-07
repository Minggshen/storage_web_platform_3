
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from storage_engine_project.config.operation_config import OperationConfig, get_default_operation_config
from storage_engine_project.config.safety_config import SafetyConfig, get_default_safety_config
from storage_engine_project.config.service_config import ServiceConfig, get_default_service_config
from storage_engine_project.data.runtime_loader import load_runtime_bundle
from storage_engine_project.data.service_loader import ServiceCalendar, load_service_calendar
from storage_engine_project.data.storage_strategy_loader import StorageStrategy, load_storage_strategies


@dataclass(slots=True)
class AnnualOperationContext:
    internal_model_id: str
    strategy: StorageStrategy
    strategy_library: dict[str, StorageStrategy] = field(default_factory=dict)

    load_matrix_kw: np.ndarray = field(default_factory=lambda: np.zeros((365, 24)))
    tariff_matrix_yuan_per_kwh: np.ndarray = field(default_factory=lambda: np.zeros((365, 24)))
    pv_matrix_kw: np.ndarray = field(default_factory=lambda: np.zeros((365, 24)))

    transformer_capacity_kva: float | None = None
    transformer_pf_limit: float = 0.95
    transformer_reserve_ratio: float = 0.15

    operation_config: OperationConfig = field(default_factory=get_default_operation_config)
    safety_config: SafetyConfig = field(default_factory=get_default_safety_config)
    service_config: ServiceConfig = field(default_factory=get_default_service_config)
    service_calendar: ServiceCalendar | None = None

    node_id: int | None = None
    scenario_name: str = ""
    category: str = ""
    q_to_p_ratio: float = 0.25
    model_year: int = 2025
    node_dir: str = ""
    runtime_payload: dict[str, Any] = field(default_factory=dict)

    include_aux_service_revenue: bool = False
    include_capacity_revenue: bool = False
    include_loss_reduction_revenue: bool = False
    include_degradation_cost: bool = True
    include_government_subsidy: bool = False
    include_replacement_cost: bool = True

    daily_demand_charge_yuan_per_kw: float = 0.0
    voltage_penalty_coeff_yuan: float = 0.0
    dispatch_mode: str = "hybrid"
    run_mode: str = "single_user"

    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ["load_matrix_kw", "tariff_matrix_yuan_per_kwh", "pv_matrix_kw"]:
            arr = np.asarray(getattr(self, name), dtype=float)
            if arr.shape != (365, 24):
                raise ValueError(f"{name} 形状必须为 (365, 24)，当前为 {arr.shape}")
            setattr(self, name, arr)

        if self.service_calendar is None:
            raise ValueError("service_calendar 不能为空。")

        if self.strategy_library and self.strategy.strategy_id not in self.strategy_library:
            self.strategy_library[self.strategy.strategy_id] = self.strategy

        self.daily_demand_charge_yuan_per_kw = float(max(0.0, self.daily_demand_charge_yuan_per_kw))
        self.voltage_penalty_coeff_yuan = float(max(0.0, self.voltage_penalty_coeff_yuan))

    @property
    def net_load_matrix_kw(self) -> np.ndarray:
        return self.load_matrix_kw - self.pv_matrix_kw

    @property
    def transformer_active_power_limit_kw(self) -> float | None:
        if self.transformer_capacity_kva is None:
            return None
        return (
            float(self.transformer_capacity_kva)
            * float(self.transformer_pf_limit)
            * max(0.0, 1.0 - float(self.transformer_reserve_ratio))
        )

    @property
    def annual_start_date(self) -> str:
        return str(self.meta.get("annual_start_date", f"{int(self.model_year)}-01-01"))

    def with_strategy(self, strategy_id: str) -> "AnnualOperationContext":
        if strategy_id not in self.strategy_library:
            raise KeyError(f"strategy_id={strategy_id} 不在 strategy_library 中。")
        return replace(self, strategy=self.strategy_library[strategy_id])


def _read_table(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{path}")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"暂不支持的文件类型：{path.suffix}")


def load_annual_tariff_matrix(file_path: str | Path) -> np.ndarray:
    df = _read_table(file_path)
    if "日期" in df.columns:
        date_col = "日期"
    elif "date" in df.columns:
        date_col = "date"
    else:
        raise ValueError("电价表缺少日期列。")

    hour_cols = [f"电价_{i:02d}" for i in range(24)]
    if not all(c in df.columns for c in hour_cols):
        hour_cols = [f"price_{i:02d}" for i in range(24)]
    if not all(c in df.columns for c in hour_cols):
        raise ValueError("电价表缺少 24 个小时电价列。")

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)
    if len(df) != 365:
        raise ValueError(f"年度电价表应为365行，当前{len(df)}行。")
    return df[hour_cols].astype(float).to_numpy()


def _build_load_and_pv_from_runtime(
    node_dir: str | Path,
    year_model_map_file: str,
    model_library_file: str,
    q_to_p_ratio: float = 0.25,
    pv_capacity_kw: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    node_dir = Path(node_dir).resolve()
    year_model_map_path = (node_dir / year_model_map_file).resolve()
    model_library_path = (node_dir / model_library_file).resolve()

    scenario_payload = {
        "year_model_map_path": str(year_model_map_path),
        "model_library_path": str(model_library_path),
        "q_to_p_ratio": q_to_p_ratio,
        "node_id": 1,
        "name": node_dir.name,
        "category": "",
    }
    payload = load_runtime_bundle(scenario_payload, project_root=None, expected_days=365)

    year_model_map = payload["year_model_map"]
    model_library = payload["model_library"]

    load_matrix = np.zeros((365, 24), dtype=float)
    for d in range(365):
        model_id = int(year_model_map[d])
        load_matrix[d, :] = np.asarray(model_library[model_id], dtype=float).reshape(24)

    pv_matrix = np.zeros((365, 24), dtype=float)
    if pv_capacity_kw > 1e-9:
        hours = np.arange(24)
        shape = np.maximum(0.0, np.sin((hours - 6) / 12.0 * np.pi))
        shape = shape / max(shape.max(), 1e-9)
        pv_matrix = pv_capacity_kw * shape.reshape(1, 24)
        pv_matrix = np.repeat(pv_matrix, 365, axis=0)

    return load_matrix, pv_matrix, payload


def _debug_print_annual_input_summary(
    load_matrix: np.ndarray,
    pv_matrix: np.ndarray,
    tariff_matrix: np.ndarray,
    internal_model_id: str,
) -> None:
    load_day_sums = np.sum(load_matrix, axis=1)
    tariff_day_sums = np.sum(tariff_matrix, axis=1)
    unique_load_days = int(np.unique(np.round(load_day_sums, 4)).size)
    unique_tariff_days = int(np.unique(np.round(tariff_day_sums, 4)).size)

    print("=" * 88)
    print(f"[年度输入摘要] 场景={internal_model_id}")
    print(f"  load_matrix shape = {load_matrix.shape}")
    print(f"  pv_matrix shape   = {pv_matrix.shape}")
    print(f"  tariff shape      = {tariff_matrix.shape}")
    print(f"  前20天负荷日电量 = {np.round(load_day_sums[:20], 4).tolist()}")
    print(f"  前20天电价日和   = {np.round(tariff_day_sums[:20], 4).tolist()}")
    print(f"  负荷唯一日数     = {unique_load_days}")
    print(f"  电价唯一日数     = {unique_tariff_days}")
    print("=" * 88)


def build_annual_operation_context(
    internal_model_id: str,
    strategy_id: str,
    node_dir: str | Path,
    year_model_map_file: str,
    model_library_file: str,
    tariff_path: str | Path,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    service_calendar_path: str | Path | None = None,
    transformer_capacity_kva: float | None = None,
    transformer_pf_limit: float = 0.95,
    transformer_reserve_ratio: float = 0.15,
    operation_config: OperationConfig | None = None,
    safety_config: SafetyConfig | None = None,
    service_config: ServiceConfig | None = None,
    q_to_p_ratio: float = 0.25,
    pv_capacity_kw: float = 0.0,
    node_id: int | None = None,
    scenario_name: str = "",
    category: str = "",
    model_year: int = 2025,
    include_aux_service_revenue: bool = False,
    include_capacity_revenue: bool = False,
    include_loss_reduction_revenue: bool = False,
    include_degradation_cost: bool = True,
    include_government_subsidy: bool = False,
    include_replacement_cost: bool = True,
    daily_demand_charge_yuan_per_kw: float = 0.0,
    voltage_penalty_coeff_yuan: float = 0.0,
    dispatch_mode: str = "hybrid",
    run_mode: str = "single_user",
    extra_meta: dict[str, Any] | None = None,
    print_input_summary: bool | None = None,
) -> AnnualOperationContext:
    operation_config = operation_config or get_default_operation_config()
    safety_config = safety_config or get_default_safety_config()
    service_config = service_config or get_default_service_config()

    strategy_lib = load_storage_strategies(strategy_library_path)
    if strategy_id not in strategy_lib:
        raise KeyError(f"未在设备策略库中找到 strategy_id={strategy_id}")

    strategy = strategy_lib[strategy_id]
    load_matrix, pv_matrix, runtime_payload = _build_load_and_pv_from_runtime(
        node_dir=node_dir,
        year_model_map_file=year_model_map_file,
        model_library_file=model_library_file,
        q_to_p_ratio=q_to_p_ratio,
        pv_capacity_kw=pv_capacity_kw,
    )
    tariff_matrix = load_annual_tariff_matrix(tariff_path)
    service_calendar = load_service_calendar(service_config, service_calendar_path)

    if print_input_summary is None:
        print_input_summary = bool(getattr(operation_config, "debug", False))
    if print_input_summary:
        _debug_print_annual_input_summary(load_matrix, pv_matrix, tariff_matrix, internal_model_id)

    meta = {
        "tariff_path": str(tariff_path),
        "strategy_library_path": str(strategy_library_path),
        "service_calendar_path": str(service_calendar_path) if service_calendar_path else None,
        "year_model_map_file": year_model_map_file,
        "model_library_file": model_library_file,
        "runtime_unique_model_count": int(np.unique(runtime_payload["year_model_map"]).size),
        "annual_start_date": f"{int(model_year)}-01-01",
    }
    if extra_meta:
        meta.update(extra_meta)

    return AnnualOperationContext(
        internal_model_id=internal_model_id,
        strategy=strategy,
        strategy_library=strategy_lib,
        load_matrix_kw=load_matrix,
        tariff_matrix_yuan_per_kwh=tariff_matrix,
        pv_matrix_kw=pv_matrix,
        transformer_capacity_kva=transformer_capacity_kva,
        transformer_pf_limit=transformer_pf_limit,
        transformer_reserve_ratio=transformer_reserve_ratio,
        operation_config=operation_config,
        safety_config=safety_config,
        service_config=service_config,
        service_calendar=service_calendar,
        node_id=node_id,
        scenario_name=scenario_name,
        category=category,
        q_to_p_ratio=q_to_p_ratio,
        model_year=model_year,
        node_dir=str(node_dir),
        runtime_payload=runtime_payload,
        include_aux_service_revenue=include_aux_service_revenue,
        include_capacity_revenue=include_capacity_revenue,
        include_loss_reduction_revenue=include_loss_reduction_revenue,
        include_degradation_cost=include_degradation_cost,
        include_government_subsidy=include_government_subsidy,
        include_replacement_cost=include_replacement_cost,
        daily_demand_charge_yuan_per_kw=daily_demand_charge_yuan_per_kw,
        voltage_penalty_coeff_yuan=voltage_penalty_coeff_yuan,
        dispatch_mode=dispatch_mode,
        run_mode=run_mode,
        meta=meta,
    )
