from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage_engine_project.data.storage_strategy_loader import StorageStrategy


@dataclass(slots=True)
class SafetyConfig:
    """
    安全约束配置。
    该配置不替代设备策略表，而是作为全局安全修正层。
    """

    # 全局 SOC 安全边际，在设备策略给定窗口基础上再收紧
    global_soc_margin: float = 0.01

    # 按安全等级对额定功率进行降额
    derate_high: float = 0.90
    derate_medium: float = 0.95
    derate_low: float = 1.00

    # 是否严格使用设备策略表内给定的 SOC/温度窗口
    enforce_strategy_soc_window: bool = True
    enforce_strategy_temperature_window: bool = True

    # 是否允许策略表中未明确给出时采用默认值
    allow_fallback_defaults: bool = True

    # 年循环软上限系数，>1 表示允许适度超用但要惩罚
    annual_cycle_soft_cap_ratio: float = 1.00

    # 温度代理惩罚系数（先占位，后面第二/三层会接入）
    temperature_proxy_penalty_yuan_per_deg_hour: float = 0.0

    # 安全场景下是否允许电网充电
    allow_grid_charging_default: bool = True

    # 服务预留裕度的最小附加要求
    min_service_headroom_ratio: float = 0.05

    def resolve_power_derate(self, safety_level: str | None) -> float:
        if not safety_level:
            return self.derate_medium if self.allow_fallback_defaults else 1.0

        level = str(safety_level).strip().lower()
        if level in {"high", "高", "高安全", "a"}:
            return self.derate_high
        if level in {"medium", "中", "中安全", "b"}:
            return self.derate_medium
        if level in {"low", "低", "低安全", "c"}:
            return self.derate_low
        return self.derate_medium if self.allow_fallback_defaults else 1.0

    def resolve_soc_bounds(
        self,
        strategy: "StorageStrategy",
    ) -> tuple[float, float]:
        soc_min = float(strategy.soc_min)
        soc_max = float(strategy.soc_max)

        if self.enforce_strategy_soc_window:
            soc_min = min(max(soc_min + self.global_soc_margin, 0.0), 1.0)
            soc_max = min(max(soc_max - self.global_soc_margin, 0.0), 1.0)

        if soc_min >= soc_max:
            raise ValueError(
                f"策略 {strategy.strategy_id} 的安全修正后 SOC 窗口非法："
                f"soc_min={soc_min:.4f}, soc_max={soc_max:.4f}"
            )
        return soc_min, soc_max


def get_default_safety_config() -> SafetyConfig:
    return SafetyConfig()