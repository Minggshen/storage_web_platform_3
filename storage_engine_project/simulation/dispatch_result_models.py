from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def _ensure_1d_float_array(name: str, value: np.ndarray | list[float], expected_len: int) -> np.ndarray:
    arr = np.asarray(value, dtype=float).reshape(-1)
    if arr.shape[0] != expected_len:
        raise ValueError(f"{name} 长度必须为 {expected_len}，当前为 {arr.shape[0]}")
    return arr


@dataclass(slots=True)
class DayAheadObjectiveBreakdown:
    """
    单日目标函数拆解。
    所有字段口径均为“日累计元”。
    """

    arbitrage_revenue_yuan: float = 0.0
    service_capacity_revenue_yuan: float = 0.0
    service_delivery_revenue_yuan: float = 0.0
    service_expected_penalty_yuan: float = 0.0

    degradation_cost_yuan: float = 0.0
    transformer_penalty_yuan: float = 0.0
    throughput_penalty_yuan: float = 0.0
    smoothness_penalty_yuan: float = 0.0
    terminal_soc_penalty_yuan: float = 0.0

    total_objective_value_yuan: float = 0.0

    @property
    def service_net_revenue_yuan(self) -> float:
        return (
            self.service_capacity_revenue_yuan
            + self.service_delivery_revenue_yuan
            - self.service_expected_penalty_yuan
        )

    @property
    def net_operating_margin_yuan(self) -> float:
        return (
            self.arbitrage_revenue_yuan
            + self.service_net_revenue_yuan
            - self.degradation_cost_yuan
            - self.transformer_penalty_yuan
            - self.throughput_penalty_yuan
            - self.smoothness_penalty_yuan
            - self.terminal_soc_penalty_yuan
        )


@dataclass(slots=True)
class DayAheadDispatchPlan:
    """
    单日日前调度结果对象。
    第三层年度协调器后续可直接逐日调用并汇总。
    """

    day_index: int
    internal_model_id: str
    strategy_id: str
    strategy_name: str

    rated_power_kw: float
    rated_energy_kwh: float
    effective_power_cap_kw: float

    soc_min: float
    soc_max: float
    initial_soc: float
    target_terminal_soc: float | None
    final_soc: float

    hour_count: int

    load_kw: np.ndarray
    pv_kw: np.ndarray
    net_load_kw: np.ndarray
    tariff_yuan_per_kwh: np.ndarray

    service_availability: np.ndarray
    service_activation_factor: np.ndarray
    service_capacity_price_yuan_per_kw: np.ndarray
    service_delivery_price_yuan_per_kwh: np.ndarray
    service_penalty_price_yuan_per_kwh: np.ndarray

    charge_kw: np.ndarray
    discharge_kw: np.ndarray
    service_commit_kw: np.ndarray
    soc_path: np.ndarray

    grid_exchange_kw: np.ndarray
    transformer_slack_kw: np.ndarray

    objective_breakdown: DayAheadObjectiveBreakdown

    solver_status: str
    used_fallback: bool = False
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        h = int(self.hour_count)
        self.load_kw = _ensure_1d_float_array("load_kw", self.load_kw, h)
        self.pv_kw = _ensure_1d_float_array("pv_kw", self.pv_kw, h)
        self.net_load_kw = _ensure_1d_float_array("net_load_kw", self.net_load_kw, h)
        self.tariff_yuan_per_kwh = _ensure_1d_float_array(
            "tariff_yuan_per_kwh", self.tariff_yuan_per_kwh, h
        )

        self.service_availability = _ensure_1d_float_array(
            "service_availability", self.service_availability, h
        )
        self.service_activation_factor = _ensure_1d_float_array(
            "service_activation_factor", self.service_activation_factor, h
        )
        self.service_capacity_price_yuan_per_kw = _ensure_1d_float_array(
            "service_capacity_price_yuan_per_kw", self.service_capacity_price_yuan_per_kw, h
        )
        self.service_delivery_price_yuan_per_kwh = _ensure_1d_float_array(
            "service_delivery_price_yuan_per_kwh", self.service_delivery_price_yuan_per_kwh, h
        )
        self.service_penalty_price_yuan_per_kwh = _ensure_1d_float_array(
            "service_penalty_price_yuan_per_kwh", self.service_penalty_price_yuan_per_kwh, h
        )

        self.charge_kw = _ensure_1d_float_array("charge_kw", self.charge_kw, h)
        self.discharge_kw = _ensure_1d_float_array("discharge_kw", self.discharge_kw, h)
        self.service_commit_kw = _ensure_1d_float_array(
            "service_commit_kw", self.service_commit_kw, h
        )
        self.grid_exchange_kw = _ensure_1d_float_array(
            "grid_exchange_kw", self.grid_exchange_kw, h
        )
        self.transformer_slack_kw = _ensure_1d_float_array(
            "transformer_slack_kw", self.transformer_slack_kw, h
        )

        soc_arr = np.asarray(self.soc_path, dtype=float).reshape(-1)
        if soc_arr.shape[0] != h + 1:
            raise ValueError(f"soc_path 长度必须为 {h + 1}，当前为 {soc_arr.shape[0]}")
        self.soc_path = soc_arr

    @property
    def charge_energy_kwh(self) -> float:
        return float(np.sum(self.charge_kw))

    @property
    def discharge_energy_kwh(self) -> float:
        return float(np.sum(self.discharge_kw))

    @property
    def service_expected_energy_kwh(self) -> float:
        return float(np.sum(self.service_commit_kw * self.service_activation_factor))

    @property
    def battery_throughput_kwh(self) -> float:
        return float(
            np.sum(self.charge_kw)
            + np.sum(self.discharge_kw)
            + np.sum(self.service_commit_kw * self.service_activation_factor)
        )

    @property
    def equivalent_full_cycles(self) -> float:
        if self.rated_energy_kwh <= 0:
            return 0.0
        return float(self.battery_throughput_kwh / (2.0 * self.rated_energy_kwh))

    @property
    def grid_import_kw(self) -> np.ndarray:
        return np.maximum(self.grid_exchange_kw, 0.0)

    @property
    def grid_export_kw(self) -> np.ndarray:
        return np.maximum(-self.grid_exchange_kw, 0.0)

    @property
    def transformer_violation_hours(self) -> float:
        return float(np.sum(self.transformer_slack_kw > 1e-9))

    @property
    def max_transformer_slack_kw(self) -> float:
        return float(np.max(self.transformer_slack_kw)) if self.transformer_slack_kw.size else 0.0

    @property
    def max_charge_kw(self) -> float:
        return float(np.max(self.charge_kw)) if self.charge_kw.size else 0.0

    @property
    def max_discharge_kw(self) -> float:
        return float(np.max(self.discharge_kw)) if self.discharge_kw.size else 0.0

    @property
    def max_service_commit_kw(self) -> float:
        return float(np.max(self.service_commit_kw)) if self.service_commit_kw.size else 0.0

    def summary_dict(self) -> dict[str, Any]:
        return {
            "day_index": self.day_index,
            "internal_model_id": self.internal_model_id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "rated_power_kw": self.rated_power_kw,
            "rated_energy_kwh": self.rated_energy_kwh,
            "effective_power_cap_kw": self.effective_power_cap_kw,
            "initial_soc": self.initial_soc,
            "target_terminal_soc": self.target_terminal_soc,
            "final_soc": self.final_soc,
            "charge_energy_kwh": self.charge_energy_kwh,
            "discharge_energy_kwh": self.discharge_energy_kwh,
            "service_expected_energy_kwh": self.service_expected_energy_kwh,
            "battery_throughput_kwh": self.battery_throughput_kwh,
            "equivalent_full_cycles": self.equivalent_full_cycles,
            "max_charge_kw": self.max_charge_kw,
            "max_discharge_kw": self.max_discharge_kw,
            "max_service_commit_kw": self.max_service_commit_kw,
            "transformer_violation_hours": self.transformer_violation_hours,
            "max_transformer_slack_kw": self.max_transformer_slack_kw,
            "solver_status": self.solver_status,
            "used_fallback": self.used_fallback,
            "arbitrage_revenue_yuan": self.objective_breakdown.arbitrage_revenue_yuan,
            "service_capacity_revenue_yuan": self.objective_breakdown.service_capacity_revenue_yuan,
            "service_delivery_revenue_yuan": self.objective_breakdown.service_delivery_revenue_yuan,
            "service_expected_penalty_yuan": self.objective_breakdown.service_expected_penalty_yuan,
            "service_net_revenue_yuan": self.objective_breakdown.service_net_revenue_yuan,
            "degradation_cost_yuan": self.objective_breakdown.degradation_cost_yuan,
            "transformer_penalty_yuan": self.objective_breakdown.transformer_penalty_yuan,
            "throughput_penalty_yuan": self.objective_breakdown.throughput_penalty_yuan,
            "smoothness_penalty_yuan": self.objective_breakdown.smoothness_penalty_yuan,
            "terminal_soc_penalty_yuan": self.objective_breakdown.terminal_soc_penalty_yuan,
            "total_objective_value_yuan": self.objective_breakdown.total_objective_value_yuan,
        }

    def to_dataframe(self) -> np.ndarray:
        """
        仅返回二维数组，第三层若需落盘可再自行转 DataFrame。
        列顺序固定，便于统一调试。
        """
        return np.column_stack(
            [
                np.arange(self.hour_count),
                self.load_kw,
                self.pv_kw,
                self.net_load_kw,
                self.tariff_yuan_per_kwh,
                self.service_availability,
                self.service_activation_factor,
                self.charge_kw,
                self.discharge_kw,
                self.service_commit_kw,
                self.grid_exchange_kw,
                self.transformer_slack_kw,
                self.soc_path[:-1],
                self.soc_path[1:],
            ]
        )
