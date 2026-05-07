from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ServiceConfig:
    """
    多收益服务配置。
    这里不假设所有用户都能参与辅助服务，因此采用场景化开关。
    """

    enable_service: bool = False
    scenario_name: str = "arbitrage_only"   # arbitrage_only / integrated_service / custom
    service_mode: str = "scenario"          # scenario / file / none

    # 默认服务参与时段（小时）
    default_available_hours: tuple[int, ...] = field(
        default_factory=lambda: tuple(range(8, 22))
    )

    # 默认价格参数（仅在未提供服务价格文件时启用）
    default_capacity_price_yuan_per_kw: float = 0.05
    default_delivery_price_yuan_per_kwh: float = 0.10
    default_penalty_price_yuan_per_kwh: float = 0.20

    # 服务强度代理量，后续第二层会把它作为保守兑现系数
    default_activation_factor: float = 0.15

    # 服务最大占用比例
    max_service_power_ratio: float = 0.30

    # 是否要求为服务预留 SOC / 功率裕度
    require_headroom: bool = True
    default_headroom_ratio: float = 0.15

    # 最低兑现要求
    delivery_score_floor: float = 0.90


def get_default_service_config() -> ServiceConfig:
    return ServiceConfig()
