from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext


@dataclass(slots=True)
class HourlyNetworkConstraint:
    """
    某一小时的网侧约束输出。
    """

    max_charge_kw: float
    max_discharge_kw: float
    service_power_cap_kw: float

    transformer_limit_kw: float | None = None
    voltage_penalty_yuan: float = 0.0

    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.max_charge_kw = float(max(0.0, self.max_charge_kw))
        self.max_discharge_kw = float(max(0.0, self.max_discharge_kw))
        self.service_power_cap_kw = float(max(0.0, self.service_power_cap_kw))
        self.voltage_penalty_yuan = float(max(0.0, self.voltage_penalty_yuan))


class NetworkConstraintOracle(ABC):
    """
    网侧约束接口。

    后续若接 OpenDSS，可在外部实现一个兼容 get_hour_constraint() 的类，
    直接替换 SimpleNetworkConstraintOracle。
    """

    @abstractmethod
    def get_hour_constraint(
        self,
        ctx: AnnualOperationContext,
        day_index: int,
        hour_index: int,
        actual_net_load_kw: float,
        planned_charge_kw: float,
        planned_discharge_kw: float,
        planned_service_kw: float,
        rated_power_kw: float,
        rated_energy_kwh: float,
        effective_power_cap_kw: float,
        current_soc: float,
        extra: dict[str, Any] | None = None,
    ) -> HourlyNetworkConstraint:
        raise NotImplementedError


@dataclass(slots=True)
class SimpleNetworkOracleConfig:
    """
    轻量级网侧约束配置。

    作用：
    1. 在未真正接 OpenDSS 前，给第三层提供稳定接口；
    2. 在大规模优化时作为快速代理层；
    3. 后续可通过 external_callback 局部替代。
    """

    # 若用户净负荷已逼近变压器上限，则收紧可充电功率
    transformer_charge_safety_margin_kw: float = 0.0

    # 电压/网损代理惩罚，按“高负荷+充电”方向进行温和惩罚
    voltage_penalty_enabled: bool = True
    voltage_penalty_yuan_per_kw_over_transformer: float = 2.0

    # 若负荷超过变压器上限，希望电池至少留出一定放电响应能力
    reserve_discharge_when_overloaded: bool = True

    # 可选外部回调（例如接 OpenDSS）
    # 返回 HourlyNetworkConstraint 或 dict
    external_callback: Callable[..., HourlyNetworkConstraint | dict[str, Any]] | None = None


class SimpleNetworkConstraintOracle(NetworkConstraintOracle):
    """
    轻量级默认网侧约束代理。

    逻辑：
    - 充电方向主要受变压器有功容量约束；
    - 放电方向原则上不受进口容量约束限制；
    - 可通过 external_callback 注入更真实的 OpenDSS 结果；
    - 未接 OpenDSS 时，也可作为快速筛选层。
    """

    def __init__(self, config: SimpleNetworkOracleConfig | None = None) -> None:
        self.config = config or SimpleNetworkOracleConfig()

    def get_hour_constraint(
        self,
        ctx: AnnualOperationContext,
        day_index: int,
        hour_index: int,
        actual_net_load_kw: float,
        planned_charge_kw: float,
        planned_discharge_kw: float,
        planned_service_kw: float,
        rated_power_kw: float,
        rated_energy_kwh: float,
        effective_power_cap_kw: float,
        current_soc: float,
        extra: dict[str, Any] | None = None,
    ) -> HourlyNetworkConstraint:
        # 先走外部回调（若有）
        if self.config.external_callback is not None:
            result = self.config.external_callback(
                ctx=ctx,
                day_index=day_index,
                hour_index=hour_index,
                actual_net_load_kw=actual_net_load_kw,
                planned_charge_kw=planned_charge_kw,
                planned_discharge_kw=planned_discharge_kw,
                planned_service_kw=planned_service_kw,
                rated_power_kw=rated_power_kw,
                rated_energy_kwh=rated_energy_kwh,
                effective_power_cap_kw=effective_power_cap_kw,
                current_soc=current_soc,
                extra=extra or {},
            )
            if isinstance(result, HourlyNetworkConstraint):
                return result
            if isinstance(result, dict):
                return HourlyNetworkConstraint(
                    max_charge_kw=float(result.get("max_charge_kw", effective_power_cap_kw)),
                    max_discharge_kw=float(result.get("max_discharge_kw", effective_power_cap_kw)),
                    service_power_cap_kw=float(result.get("service_power_cap_kw", effective_power_cap_kw)),
                    transformer_limit_kw=result.get("transformer_limit_kw"),
                    voltage_penalty_yuan=float(result.get("voltage_penalty_yuan", 0.0)),
                    notes=list(result.get("notes", [])),
                    metadata=dict(result.get("metadata", {})),
                )
            raise TypeError("external_callback 返回类型必须为 HourlyNetworkConstraint 或 dict。")

        limit = ctx.transformer_active_power_limit_kw
        notes: list[str] = []
        metadata: dict[str, Any] = {}

        max_charge_kw = float(effective_power_cap_kw)
        max_discharge_kw = float(effective_power_cap_kw)
        service_cap_kw = float(effective_power_cap_kw)

        voltage_penalty_yuan = 0.0

        if ctx.operation_config.enable_transformer_limit and limit is not None:
            limit = float(limit)
            # 当前负荷越高，可用于继续充电的头寸越小
            charge_headroom = limit - float(actual_net_load_kw) - float(
                self.config.transformer_charge_safety_margin_kw
            )
            max_charge_kw = min(max_charge_kw, max(0.0, charge_headroom))
            notes.append("已按变压器有功上限收紧充电头寸。")

            if (
                self.config.reserve_discharge_when_overloaded
                and actual_net_load_kw > limit
            ):
                notes.append("当前负荷超过变压器限值，建议优先保留放电能力。")

            if self.config.voltage_penalty_enabled:
                overload_proxy_kw = max(0.0, actual_net_load_kw + planned_charge_kw - limit)
                voltage_penalty_yuan = (
                    float(self.config.voltage_penalty_yuan_per_kw_over_transformer)
                    * overload_proxy_kw
                )

            metadata["proxy_transformer_over_kw"] = max(0.0, actual_net_load_kw - limit)
        else:
            limit = None

        # 服务容量也共享额定功率，不宜高于可用功率上限
        service_cap_kw = min(service_cap_kw, effective_power_cap_kw)

        return HourlyNetworkConstraint(
            max_charge_kw=max_charge_kw,
            max_discharge_kw=max_discharge_kw,
            service_power_cap_kw=service_cap_kw,
            transformer_limit_kw=limit,
            voltage_penalty_yuan=voltage_penalty_yuan,
            notes=notes,
            metadata=metadata,
        )