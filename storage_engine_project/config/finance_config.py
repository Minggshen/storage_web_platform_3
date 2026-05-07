from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class StorageOperationConfig:
    """储能运行参数。"""

    eta_charge: float = 0.95
    eta_discharge: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.90
    soc_init: float = 0.50
    candidate_durations_h: Tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0)

    def __post_init__(self) -> None:
        if not (0.0 < self.eta_charge <= 1.0):
            raise ValueError("eta_charge 必须在 (0, 1] 区间。")
        if not (0.0 < self.eta_discharge <= 1.0):
            raise ValueError("eta_discharge 必须在 (0, 1] 区间。")
        if not (0.0 <= self.soc_min < 1.0):
            raise ValueError("soc_min 必须在 [0, 1) 区间。")
        if not (0.0 < self.soc_max <= 1.0):
            raise ValueError("soc_max 必须在 (0, 1] 区间。")
        if not (self.soc_min < self.soc_max):
            raise ValueError("soc_max 必须严格大于 soc_min。")
        if not (self.soc_min <= self.soc_init <= self.soc_max):
            raise ValueError("soc_init 必须位于 [soc_min, soc_max] 区间内。")
        durations = [float(x) for x in self.candidate_durations_h]
        if not durations:
            raise ValueError("candidate_durations_h 不能为空。")
        if any(x <= 0 for x in durations):
            raise ValueError("candidate_durations_h 中存在非正值。")
        if durations != sorted(durations):
            raise ValueError("candidate_durations_h 必须按从小到大排序。")
        if len(set(durations)) != len(durations):
            raise ValueError("candidate_durations_h 中不能重复。")


@dataclass(frozen=True)
class SafetyDesignProfile:
    """防火防爆高安全设备模板。"""

    profile_name: str
    profile_label: str
    battery_chemistry: str
    thermal_management: str
    fire_suppression: str
    gas_detection: str
    explosion_relief: str
    bms_redundancy: str

    energy_side_capex_multiplier: float = 1.0
    power_side_capex_multiplier: float = 1.0
    station_integration_capex_multiplier: float = 1.0
    fire_protection_capex_multiplier: float = 1.0

    gas_detection_capex_yuan_per_kwh: float = 0.0
    explosion_relief_capex_yuan_per_kwh: float = 0.0
    thermal_management_upgrade_capex_yuan_per_kwh: float = 0.0
    bms_redundancy_capex_yuan_per_kwh: float = 0.0

    annual_insurance_rate_on_capex: float = 0.003
    annual_safety_maintenance_rate_on_capex: float = 0.002
    annual_fire_system_inspection_rate_on_capex: float = 0.001

    availability_factor: float = 1.0
    throughput_revenue_factor: float = 1.0
    cycle_limit_factor: float = 1.0

    recommended_soc_min: float = 0.10
    recommended_soc_max: float = 0.90
    max_recommended_duration_h: float = 4.0
    safety_rank: float = 1.0

    def __post_init__(self) -> None:
        nonnegative_names = (
            "energy_side_capex_multiplier", "power_side_capex_multiplier",
            "station_integration_capex_multiplier", "fire_protection_capex_multiplier",
            "gas_detection_capex_yuan_per_kwh", "explosion_relief_capex_yuan_per_kwh",
            "thermal_management_upgrade_capex_yuan_per_kwh", "bms_redundancy_capex_yuan_per_kwh",
            "annual_insurance_rate_on_capex", "annual_safety_maintenance_rate_on_capex",
            "annual_fire_system_inspection_rate_on_capex", "safety_rank",
        )
        for name in nonnegative_names:
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} 不能为负。")

        for name in ("availability_factor", "throughput_revenue_factor", "cycle_limit_factor"):
            value = float(getattr(self, name))
            if not (0.0 < value <= 1.0):
                raise ValueError(f"{name} 必须在 (0, 1]。")

        if not (0.0 <= self.recommended_soc_min < self.recommended_soc_max <= 1.0):
            raise ValueError("安全模板推荐 SOC 上下限设置错误。")
        if self.max_recommended_duration_h <= 0:
            raise ValueError("max_recommended_duration_h 必须大于 0。")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_label": self.profile_label,
            "battery_chemistry": self.battery_chemistry,
            "thermal_management": self.thermal_management,
            "fire_suppression": self.fire_suppression,
            "gas_detection": self.gas_detection,
            "explosion_relief": self.explosion_relief,
            "bms_redundancy": self.bms_redundancy,
            "energy_side_capex_multiplier": self.energy_side_capex_multiplier,
            "power_side_capex_multiplier": self.power_side_capex_multiplier,
            "station_integration_capex_multiplier": self.station_integration_capex_multiplier,
            "fire_protection_capex_multiplier": self.fire_protection_capex_multiplier,
            "gas_detection_capex_yuan_per_kwh": self.gas_detection_capex_yuan_per_kwh,
            "explosion_relief_capex_yuan_per_kwh": self.explosion_relief_capex_yuan_per_kwh,
            "thermal_management_upgrade_capex_yuan_per_kwh": self.thermal_management_upgrade_capex_yuan_per_kwh,
            "bms_redundancy_capex_yuan_per_kwh": self.bms_redundancy_capex_yuan_per_kwh,
            "annual_insurance_rate_on_capex": self.annual_insurance_rate_on_capex,
            "annual_safety_maintenance_rate_on_capex": self.annual_safety_maintenance_rate_on_capex,
            "annual_fire_system_inspection_rate_on_capex": self.annual_fire_system_inspection_rate_on_capex,
            "availability_factor": self.availability_factor,
            "throughput_revenue_factor": self.throughput_revenue_factor,
            "cycle_limit_factor": self.cycle_limit_factor,
            "recommended_soc_min": self.recommended_soc_min,
            "recommended_soc_max": self.recommended_soc_max,
            "max_recommended_duration_h": self.max_recommended_duration_h,
            "safety_rank": self.safety_rank,
        }


@dataclass(frozen=True)
class EconomicConfig:
    """
    经济参数总配置。

    说明：
    1. 是否启用某项收益由 node_registry.xlsx 中的注册表开关控制；
    2. 对应收益单价优先来自前端写入的注册表字段；
    3. 本文件只保留和前端一致的参考默认值，用于旧数据缺字段时兜底。
    """

    # 能量侧设备价（元/kWh）
    system_price_curve_yuan_per_kwh: Tuple[Tuple[float, float], ...] = (
        (1.0, 960.0),
        (2.0, 800.0),
        (3.0, 715.0),
        (4.0, 650.0),
    )
    duration_interp_method: str = "linear"

    # 其他 CAPEX
    power_related_capex_yuan_per_kw: float = 300.0
    station_integration_capex_ratio: float = 0.15
    fire_protection_capex_ratio: float = 0.02

    # 财务参数
    maintenance_rate: float = 0.0
    discount_rate: float = 0.06
    lifetime_years: int = 20

    # 收益参数（由注册表决定是否启用；此处定义单价）
    # 说明：
    # 1. auxiliary_service_price_yuan_per_kwh 保留为兼容旧字段；
    # 2. demand_response / vpp_service 才是当前工商业用户侧更推荐的显式收益项；
    # 3. allow_non_user_side_revenue=False 时，容量/网损等非用户侧收益默认不纳入现金流。
    auxiliary_service_price_yuan_per_kwh: float = 0.00
    demand_response_price_yuan_per_kwh: float = 0.00
    vpp_service_price_yuan_per_kwh: float = 0.00
    capacity_service_price_yuan_per_kw_day: float = 0.00
    demand_charge_yuan_per_kw_month: float = 48.0
    network_loss_price_yuan_per_kwh: float = 0.30
    allow_non_user_side_revenue: bool = False

    # 运维
    annual_fixed_om_yuan_per_kw_year: float = 18.0
    annual_variable_om_yuan_per_kwh: float = 0.004

    # 补贴
    government_subsidy_rate_on_capex: float = 0.0
    government_subsidy_yuan_per_kwh: float = 0.0
    government_subsidy_yuan_per_kw: float = 0.0
    government_subsidy_cap_yuan: float = 0.0

    # 退化与更换
    battery_capex_share: float = 0.60
    cycle_life_efc: float = 8000.0
    calendar_life_years: float = 20.0
    calendar_fade_share: float = 0.15
    min_degradation_cost_ratio: float = 0.0

    replacement_trigger_soh: float = 0.70
    replacement_reset_soh: float = 0.95
    replacement_cost_ratio_of_battery_capex: float = 0.60
    replacement_installation_cost_ratio_of_initial_capex: float = 0.03

    # 推荐方案筛选参数
    common_scheme_min_npv_ratio: float = 0.85
    safe_scheme_min_npv_ratio: float = 0.60
    safe_scheme_max_payback_years: float = 12.0
    safe_scheme_score_weights: Tuple[float, float, float, float, float] = (0.18, 0.18, 0.22, 0.22, 0.20)

    common_safety_profile: SafetyDesignProfile = field(default_factory=lambda: SafetyDesignProfile(
        profile_name="common",
        profile_label="常用设备方案",
        battery_chemistry="磷酸铁锂（常规工商业电柜）",
        thermal_management="标准液冷/风冷",
        fire_suppression="舱级灭火",
        gas_detection="单套烟感+可燃气体探测",
        explosion_relief="基础泄压设计",
        bms_redundancy="标准 BMS",
        energy_side_capex_multiplier=1.00,
        power_side_capex_multiplier=1.00,
        station_integration_capex_multiplier=1.00,
        fire_protection_capex_multiplier=1.00,
        gas_detection_capex_yuan_per_kwh=5.0,
        explosion_relief_capex_yuan_per_kwh=4.0,
        thermal_management_upgrade_capex_yuan_per_kwh=8.0,
        bms_redundancy_capex_yuan_per_kwh=5.0,
        annual_insurance_rate_on_capex=0.0040,
        annual_safety_maintenance_rate_on_capex=0.0020,
        annual_fire_system_inspection_rate_on_capex=0.0010,
        availability_factor=0.99,
        throughput_revenue_factor=0.99,
        cycle_limit_factor=0.99,
        recommended_soc_min=0.10,
        recommended_soc_max=0.90,
        max_recommended_duration_h=4.0,
        safety_rank=0.70,
    ))

    high_safety_profile: SafetyDesignProfile = field(default_factory=lambda: SafetyDesignProfile(
        profile_name="high_safety",
        profile_label="高安全设备方案",
        battery_chemistry="磷酸铁锂（高安全等级）",
        thermal_management="液冷 + 簇级热隔离",
        fire_suppression="Pack/舱级双层灭火",
        gas_detection="烟温 + 可燃气体 + VOC 冗余探测",
        explosion_relief="防爆泄压 + 定向排风",
        bms_redundancy="主备 BMS + 故障切除",
        energy_side_capex_multiplier=1.05,
        power_side_capex_multiplier=1.03,
        station_integration_capex_multiplier=1.06,
        fire_protection_capex_multiplier=1.80,
        gas_detection_capex_yuan_per_kwh=14.0,
        explosion_relief_capex_yuan_per_kwh=10.0,
        thermal_management_upgrade_capex_yuan_per_kwh=26.0,
        bms_redundancy_capex_yuan_per_kwh=12.0,
        annual_insurance_rate_on_capex=0.0036,
        annual_safety_maintenance_rate_on_capex=0.0032,
        annual_fire_system_inspection_rate_on_capex=0.0016,
        availability_factor=0.985,
        throughput_revenue_factor=0.975,
        cycle_limit_factor=0.95,
        recommended_soc_min=0.15,
        recommended_soc_max=0.85,
        max_recommended_duration_h=3.5,
        safety_rank=0.95,
    ))

    def __post_init__(self) -> None:
        durations = [pt[0] for pt in self.system_price_curve_yuan_per_kwh]
        prices = [pt[1] for pt in self.system_price_curve_yuan_per_kwh]
        if not durations:
            raise ValueError("system_price_curve_yuan_per_kwh 不能为空。")
        if any(d <= 0 for d in durations):
            raise ValueError("system_price_curve_yuan_per_kwh 中存在非正时长。")
        if any(p <= 0 for p in prices):
            raise ValueError("system_price_curve_yuan_per_kwh 中存在非正价格。")
        if durations != sorted(durations):
            raise ValueError("system_price_curve_yuan_per_kwh 必须按时长排序。")
        if self.duration_interp_method not in {"linear", "nearest"}:
            raise ValueError("duration_interp_method 仅支持 linear / nearest。")
        for name in (
            "power_related_capex_yuan_per_kw", "station_integration_capex_ratio", "fire_protection_capex_ratio",
            "maintenance_rate", "discount_rate", "auxiliary_service_price_yuan_per_kwh",
            "demand_response_price_yuan_per_kwh", "vpp_service_price_yuan_per_kwh",
            "capacity_service_price_yuan_per_kw_day", "demand_charge_yuan_per_kw_month", "network_loss_price_yuan_per_kwh",
            "annual_fixed_om_yuan_per_kw_year", "annual_variable_om_yuan_per_kwh",
            "government_subsidy_rate_on_capex", "government_subsidy_yuan_per_kwh", "government_subsidy_yuan_per_kw",
            "government_subsidy_cap_yuan", "battery_capex_share", "cycle_life_efc", "calendar_life_years",
            "calendar_fade_share", "min_degradation_cost_ratio", "replacement_trigger_soh", "replacement_reset_soh",
            "replacement_cost_ratio_of_battery_capex", "replacement_installation_cost_ratio_of_initial_capex",
            "common_scheme_min_npv_ratio", "safe_scheme_min_npv_ratio", "safe_scheme_max_payback_years",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} 不能为负。")
        if self.lifetime_years <= 0:
            raise ValueError("lifetime_years 必须大于 0。")
        if not (0.0 <= self.battery_capex_share <= 1.0):
            raise ValueError("battery_capex_share 必须在 [0, 1]。")
        if not (0.0 <= self.calendar_fade_share <= 1.0):
            raise ValueError("calendar_fade_share 必须在 [0, 1]。")
        if not (0.0 < self.replacement_trigger_soh < self.replacement_reset_soh <= 1.0):
            raise ValueError("replacement SOH 参数设置错误。")


@dataclass(frozen=True)
class FinanceConfig:
    storage: StorageOperationConfig = field(default_factory=StorageOperationConfig)
    economics: EconomicConfig = field(default_factory=EconomicConfig)

    def to_flat_dict(self) -> Dict[str, Any]:
        return {
            "eta_charge": self.storage.eta_charge,
            "eta_discharge": self.storage.eta_discharge,
            "soc_min": self.storage.soc_min,
            "soc_max": self.storage.soc_max,
            "soc_init": self.storage.soc_init,
            "SOC_min": self.storage.soc_min,
            "SOC_max": self.storage.soc_max,
            "SOC_init": self.storage.soc_init,
            "candidate_durations_h": self.storage.candidate_durations_h,
            "system_price_curve_yuan_per_kwh": self.economics.system_price_curve_yuan_per_kwh,
            "duration_interp_method": self.economics.duration_interp_method,
            "maintenance_rate": self.economics.maintenance_rate,
            "discount_rate": self.economics.discount_rate,
            "lifetime_years": self.economics.lifetime_years,
            "lifetime": self.economics.lifetime_years,
            "price_aux": self.economics.auxiliary_service_price_yuan_per_kwh,
            "price_demand_response": self.economics.demand_response_price_yuan_per_kwh,
            "price_vpp_service": self.economics.vpp_service_price_yuan_per_kwh,
            "price_cap_daily": self.economics.capacity_service_price_yuan_per_kw_day,
            "price_demand": self.economics.demand_charge_yuan_per_kw_month,
            "price_loss": self.economics.network_loss_price_yuan_per_kwh,
            "auxiliary_service_price_yuan_per_kwh": self.economics.auxiliary_service_price_yuan_per_kwh,
            "demand_response_price_yuan_per_kwh": self.economics.demand_response_price_yuan_per_kwh,
            "vpp_service_price_yuan_per_kwh": self.economics.vpp_service_price_yuan_per_kwh,
            "capacity_service_price_yuan_per_kw_day": self.economics.capacity_service_price_yuan_per_kw_day,
            "demand_charge_yuan_per_kw_month": self.economics.demand_charge_yuan_per_kw_month,
            "network_loss_price_yuan_per_kwh": self.economics.network_loss_price_yuan_per_kwh,
            "allow_non_user_side_revenue": self.economics.allow_non_user_side_revenue,
            "power_related_capex_yuan_per_kw": self.economics.power_related_capex_yuan_per_kw,
            "station_integration_capex_ratio": self.economics.station_integration_capex_ratio,
            "fire_protection_capex_ratio": self.economics.fire_protection_capex_ratio,
            "annual_fixed_om_yuan_per_kw_year": self.economics.annual_fixed_om_yuan_per_kw_year,
            "annual_variable_om_yuan_per_kwh": self.economics.annual_variable_om_yuan_per_kwh,
            "government_subsidy_rate_on_capex": self.economics.government_subsidy_rate_on_capex,
            "government_subsidy_yuan_per_kwh": self.economics.government_subsidy_yuan_per_kwh,
            "government_subsidy_yuan_per_kw": self.economics.government_subsidy_yuan_per_kw,
            "government_subsidy_cap_yuan": self.economics.government_subsidy_cap_yuan,
            "battery_capex_share": self.economics.battery_capex_share,
            "cycle_life_efc": self.economics.cycle_life_efc,
            "calendar_life_years": self.economics.calendar_life_years,
            "calendar_fade_share": self.economics.calendar_fade_share,
            "min_degradation_cost_ratio": self.economics.min_degradation_cost_ratio,
            "replacement_trigger_soh": self.economics.replacement_trigger_soh,
            "replacement_reset_soh": self.economics.replacement_reset_soh,
            "replacement_cost_ratio_of_battery_capex": self.economics.replacement_cost_ratio_of_battery_capex,
            "replacement_installation_cost_ratio_of_initial_capex": self.economics.replacement_installation_cost_ratio_of_initial_capex,
            "common_scheme_min_npv_ratio": self.economics.common_scheme_min_npv_ratio,
            "safe_scheme_min_npv_ratio": self.economics.safe_scheme_min_npv_ratio,
            "safe_scheme_max_payback_years": self.economics.safe_scheme_max_payback_years,
            "safe_scheme_score_weights": self.economics.safe_scheme_score_weights,
            "common_safety_profile": self.economics.common_safety_profile.to_dict(),
            "high_safety_profile": self.economics.high_safety_profile.to_dict(),
        }

    def to_legacy_dict(self) -> Dict[str, Any]:
        return self.to_flat_dict()


def get_default_finance_config() -> FinanceConfig:
    return FinanceConfig()
