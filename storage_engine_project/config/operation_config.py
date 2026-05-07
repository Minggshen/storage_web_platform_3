from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OperationConfig:
    annual_days: int = 365
    hours_per_day: int = 24

    day_ahead_step_hours: int = 1
    rolling_step_minutes: int = 60
    use_rolling_dispatch: bool = True

    enforce_daily_terminal_soc: bool = True
    daily_terminal_soc_tolerance: float = 0.02

    # free / carry / fixed / strategy_mid / weekly_anchor / monthly_anchor / blended_anchor
    terminal_soc_mode: str = "weekly_anchor"

    fixed_terminal_soc_target: float = 0.50
    anchor_soc_target: float = 0.50

    anchor_cycle_days: int = 7
    anchor_day_index: int = 6
    interday_soc_reversion_weight: float = 0.35

    enable_terminal_soc_correction: bool = True
    terminal_soc_correction_hours: int = 4

    enable_transformer_limit: bool = True
    enable_voltage_penalty: bool = True
    use_network_oracle: bool = True
    network_recheck_interval_hours: int = 1

    fast_screen_mode: bool = False
    debug: bool = False

    @property
    def rolling_steps_per_hour(self) -> int:
        return max(1, 60 // self.rolling_step_minutes)

    @property
    def rolling_steps_per_day(self) -> int:
        return self.hours_per_day * self.rolling_steps_per_hour


def get_default_operation_config() -> OperationConfig:
    """
    兼容旧代码入口。
    某些模块（如 case_builder.py）仍会导入这个函数，
    因此这里保留一个默认配置构造函数。
    """
    return OperationConfig()
