from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext


@dataclass(slots=True)
class DailyServiceProfile:
    """
    单日服务参与画像。
    这是第二层调度器和第三层年度协调器之间的重要中间对象。
    """

    enabled: bool
    availability: np.ndarray                          # 24
    capacity_price_yuan_per_kw: np.ndarray            # 24
    delivery_price_yuan_per_kwh: np.ndarray           # 24
    penalty_price_yuan_per_kwh: np.ndarray            # 24
    activation_factor: np.ndarray                     # 24

    max_service_power_kw: float
    headroom_ratio: float
    expected_penalty_ratio: float

    def __post_init__(self) -> None:
        for name in [
            "availability",
            "capacity_price_yuan_per_kw",
            "delivery_price_yuan_per_kwh",
            "penalty_price_yuan_per_kwh",
            "activation_factor",
        ]:
            arr = np.asarray(getattr(self, name), dtype=float).reshape(-1)
            if arr.shape[0] != 24:
                raise ValueError(f"{name} 长度必须为 24，当前为 {arr.shape[0]}")
            setattr(self, name, arr)

        self.max_service_power_kw = float(max(0.0, self.max_service_power_kw))
        self.headroom_ratio = float(max(0.0, self.headroom_ratio))
        self.expected_penalty_ratio = float(np.clip(self.expected_penalty_ratio, 0.0, 1.0))

    @property
    def net_service_value_yuan_per_kw(self) -> np.ndarray:
        """
        单位承诺功率的净收益代理值，口径为 元/(kW·h)。

        计算式：
        容量收益 + 激活系数 * (兑现收益 - 期望惩罚)
        """
        return (
            self.capacity_price_yuan_per_kw
            + self.activation_factor
            * (
                self.delivery_price_yuan_per_kwh
                - self.expected_penalty_ratio * self.penalty_price_yuan_per_kwh
            )
        )

    @property
    def active_hours(self) -> np.ndarray:
        return np.where(self.availability > 1e-9)[0]

    @property
    def has_any_service_hour(self) -> bool:
        return bool(np.any(self.availability > 1e-9))


def build_daily_service_profile(
    ctx: AnnualOperationContext,
    day_index: int,
    effective_power_cap_kw: float,
) -> DailyServiceProfile:
    """
    从年度上下文构造某一天的服务参与画像。
    """
    strategy = ctx.strategy
    svc_cfg = ctx.service_config
    safe_cfg = ctx.safety_config
    cal = ctx.service_calendar

    if not svc_cfg.enable_service:
        return _build_disabled_profile()

    if not strategy.allow_service:
        return _build_disabled_profile()

    if effective_power_cap_kw <= 0:
        return _build_disabled_profile()

    availability = np.asarray(cal.availability_matrix[day_index], dtype=float).reshape(24)
    availability = np.clip(availability, 0.0, 1.0)

    cap_price = np.asarray(
        cal.capacity_price_matrix_yuan_per_kw[day_index], dtype=float
    ).reshape(24)
    del_price = np.asarray(
        cal.delivery_price_matrix_yuan_per_kwh[day_index], dtype=float
    ).reshape(24)
    pen_price = np.asarray(
        cal.penalty_price_matrix_yuan_per_kwh[day_index], dtype=float
    ).reshape(24)
    activation = np.asarray(
        cal.activation_factor_matrix[day_index], dtype=float
    ).reshape(24)
    activation = np.clip(activation, 0.0, 1.0)

    max_service_power_kw = effective_power_cap_kw * float(svc_cfg.max_service_power_ratio)
    max_service_power_kw = max(0.0, max_service_power_kw)

    # 头寸预留比例：策略表与全局配置中取更严格者
    if svc_cfg.require_headroom:
        headroom_ratio = max(
            float(strategy.service_headroom_ratio),
            float(svc_cfg.default_headroom_ratio),
            float(safe_cfg.min_service_headroom_ratio),
        )
    else:
        headroom_ratio = 0.0

    expected_penalty_ratio = max(0.0, 1.0 - float(svc_cfg.delivery_score_floor))

    if max_service_power_kw <= 1e-9 or np.all(availability <= 1e-9):
        return _build_disabled_profile()

    return DailyServiceProfile(
        enabled=True,
        availability=availability,
        capacity_price_yuan_per_kw=cap_price,
        delivery_price_yuan_per_kwh=del_price,
        penalty_price_yuan_per_kwh=pen_price,
        activation_factor=activation,
        max_service_power_kw=max_service_power_kw,
        headroom_ratio=headroom_ratio,
        expected_penalty_ratio=expected_penalty_ratio,
    )


def service_soc_reserve_ratio_expr(
    service_commit_kw,
    effective_power_cap_kw: float,
    headroom_ratio: float,
):
    """
    返回服务承诺对应的 SOC 预留比例表达式。

    解释：
    当服务承诺功率越接近可用功率上限，SOC 距离上下边界应越远；
    这里采用线性比例近似，避免引入高复杂度非线性或混合整数约束。

    reserve_soc_ratio = headroom_ratio * service_commit / effective_power_cap
    """
    denom = max(float(effective_power_cap_kw), 1e-6)
    return float(headroom_ratio) * service_commit_kw / denom


def _build_disabled_profile() -> DailyServiceProfile:
    zeros = np.zeros(24, dtype=float)
    return DailyServiceProfile(
        enabled=False,
        availability=zeros,
        capacity_price_yuan_per_kw=zeros,
        delivery_price_yuan_per_kwh=zeros,
        penalty_price_yuan_per_kwh=zeros,
        activation_factor=zeros,
        max_service_power_kw=0.0,
        headroom_ratio=0.0,
        expected_penalty_ratio=0.0,
    )