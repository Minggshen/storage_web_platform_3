from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from storage_engine_project.economics.economic_result_models import LifecycleFinancialResult
from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationResult


@dataclass(slots=True)
class StorageDecision:
    """
    外层优化的单个候选决策。
    """

    strategy_id: str
    rated_power_kw: float
    rated_energy_kwh: float

    def duration_h(self) -> float:
        if self.rated_power_kw <= 0:
            raise ValueError("rated_power_kw 必须大于 0。")
        return float(self.rated_energy_kwh / self.rated_power_kw)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "rated_power_kw": float(self.rated_power_kw),
            "rated_energy_kwh": float(self.rated_energy_kwh),
            "duration_h": float(self.duration_h()),
        }


@dataclass(slots=True)
class ScreeningResult:
    """
    快速筛选结果。
    """

    is_feasible: bool
    messages: list[str] = field(default_factory=list)
    score_hint: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def reason_text(self) -> str:
        return "；".join(self.messages)


@dataclass(slots=True)
class ObjectiveVector:
    """
    外层优化目标向量。
    约定全部转为“最小化”口径：
    - obj_npv = -NPV
    - obj_payback = payback
    - obj_investment = initial investment
    - obj_safety = safety penalty / grid-impact proxy
    """

    obj_npv: float
    obj_payback: float
    obj_investment: float
    obj_safety: float = 0.0

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (
            float(self.obj_npv),
            float(self.obj_payback),
            float(self.obj_investment),
            float(self.obj_safety),
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "obj_npv": float(self.obj_npv),
            "obj_payback": float(self.obj_payback),
            "obj_investment": float(self.obj_investment),
            "obj_safety": float(self.obj_safety),
        }


@dataclass(slots=True)
class ConstraintVector:
    """
    约束违背向量（分层优先级）。
    约定：
    - <= 0 表示满足；
    - > 0 表示违反量。
    
    优先级分层：
    - 硬约束（P1）：电网安全约束，必须满足
    - 中等约束（P2）：设备技术约束，强烈建议满足
    - 软约束（P3）：经济性约束，可适度放宽
    """

    # P1: 硬约束 - 电网安全
    voltage_violation_pu: float = 0.0
    line_loading_violation_pct: float = 0.0
    transformer_violation_hours: float = 0.0
    transformer_slack_kw: float = 0.0
    
    # P2: 中等约束 - 设备技术
    duration_violation_h: float = 0.0
    cycle_violation: float = 0.0
    
    # P3: 软约束 - 经济性
    negative_cashflow_violation: float = 0.0
    payback_violation_years: float = 0.0

    def max_violation(self) -> float:
        return max(
            float(self.voltage_violation_pu),
            float(self.line_loading_violation_pct),
            float(self.transformer_violation_hours),
            float(self.transformer_slack_kw),
            float(self.duration_violation_h),
            float(self.cycle_violation),
            float(self.negative_cashflow_violation),
            float(self.payback_violation_years),
        )

    def hard_constraint_violation(self) -> float:
        """P1硬约束总违背量（电网安全）"""
        return (
            max(0.0, float(self.voltage_violation_pu)) * 1000.0  # 高权重
            + max(0.0, float(self.line_loading_violation_pct)) * 100.0
            + max(0.0, float(self.transformer_violation_hours)) * 10.0
            + max(0.0, float(self.transformer_slack_kw)) * 0.1
        )
    
    def medium_constraint_violation(self) -> float:
        """P2中等约束总违背量（设备技术）"""
        return (
            max(0.0, float(self.duration_violation_h)) * 10.0
            + max(0.0, float(self.cycle_violation)) * 5.0
        )
    
    def soft_constraint_violation(self) -> float:
        """P3软约束总违背量（经济性）"""
        return (
            max(0.0, float(self.negative_cashflow_violation)) * 0.01
            + max(0.0, float(self.payback_violation_years)) * 0.1
        )

    def total_violation(self) -> float:
        """分层加权总违背量"""
        return (
            self.hard_constraint_violation() * 1e6  # 硬约束最高优先级
            + self.medium_constraint_violation() * 1e3  # 中等约束次之
            + self.soft_constraint_violation()  # 软约束最低
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "duration_violation_h": float(self.duration_violation_h),
            "cycle_violation": float(self.cycle_violation),
            "transformer_violation_hours": float(self.transformer_violation_hours),
            "transformer_slack_kw": float(self.transformer_slack_kw),
            "voltage_violation_pu": float(self.voltage_violation_pu),
            "line_loading_violation_pct": float(self.line_loading_violation_pct),
            "negative_cashflow_violation": float(self.negative_cashflow_violation),
            "payback_violation_years": float(self.payback_violation_years),
            "max_violation": float(self.max_violation()),
            "total_violation": float(self.total_violation()),
        }


@dataclass(slots=True)
class FitnessEvaluationResult:
    """
    单个候选方案的完整评估结果。
    """

    decision: StorageDecision
    screening_result: ScreeningResult

    objective_vector: ObjectiveVector
    constraint_vector: ConstraintVector

    annual_operation_result: AnnualOperationResult | None = None
    lifecycle_financial_result: LifecycleFinancialResult | None = None

    is_valid: bool = True
    used_fast_reject: bool = False
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return self.is_valid and self.constraint_vector.max_violation() <= 0.0

    def summary_dict(self) -> dict[str, Any]:
        base = {
            **self.decision.summary_dict(),
            "is_valid": bool(self.is_valid),
            "feasible": bool(self.feasible),
            "used_fast_reject": bool(self.used_fast_reject),
            **self.objective_vector.as_dict(),
            **self.constraint_vector.as_dict(),
            "screening_messages": list(self.screening_result.messages),
            "notes": list(self.notes),
        }

        if self.lifecycle_financial_result is not None:
            fin = self.lifecycle_financial_result.summary_dict()
            base.update(
                {
                    "npv_yuan": fin["npv_yuan"],
                    "irr": fin["irr"],
                    "simple_payback_years": fin["simple_payback_years"],
                    "discounted_payback_years": fin["discounted_payback_years"],
                    "initial_investment_yuan": fin["initial_investment_yuan"],
                    "annualized_net_cashflow_yuan": fin["annualized_net_cashflow_yuan"],
                    "lc_net_profit_yuan": fin["lc_net_profit_yuan"],
                }
            )
            for key in (
                "government_subsidy_yuan",
                "initial_net_investment_yuan",
                "total_replacement_cost_yuan",
                "annual_replacement_equivalent_cost_yuan",
                "replacement_year_effective",
                "cycle_life_efc_effective",
                "replacement_trigger_soh_effective",
                "replacement_reset_soh_effective",
                "first_year_capacity_factor",
                "last_year_capacity_factor",
                "annual_auxiliary_service_revenue_yuan",
                "annual_capacity_revenue_yuan",
                "annual_loss_reduction_revenue_yuan",
                "annual_demand_saving_yuan",
                "annual_degradation_cost_yuan",
                "annual_om_cost_yuan",
            ):
                if key in fin:
                    base[key] = fin[key]

        if self.annual_operation_result is not None:
            ann = self.annual_operation_result.summary_dict()
            base.update(
                {
                    "annual_net_operating_cashflow_yuan": ann["annual_net_operating_cashflow_yuan"],
                    "annual_equivalent_full_cycles": ann["annual_equivalent_full_cycles"],
                    "annual_battery_throughput_kwh": ann["annual_battery_throughput_kwh"],
                    "transformer_violation_hours_runtime": ann["transformer_violation_hours"],
                    "max_transformer_slack_kw_runtime": ann["max_transformer_slack_kw"],
                    "max_voltage_violation_pu_runtime": ann["max_voltage_violation_pu"],
                    "max_baseline_voltage_violation_pu_runtime": ann["max_baseline_voltage_violation_pu"],
                    "max_storage_voltage_violation_increment_pu_runtime": ann[
                        "max_storage_voltage_violation_increment_pu"
                    ],
                    "max_line_loading_pct_runtime": ann["max_line_loading_pct"],
                    "max_line_overload_pct_runtime": ann["max_line_overload_pct"],
                    "max_baseline_line_loading_pct_runtime": ann["max_baseline_line_loading_pct"],
                    "max_baseline_line_overload_pct_runtime": ann["max_baseline_line_overload_pct"],
                    "max_baseline_target_voltage_violation_pu_runtime": ann[
                        "max_baseline_target_voltage_violation_pu"
                    ],
                    "max_target_voltage_violation_pu_runtime": ann["max_target_voltage_violation_pu"],
                    "max_storage_target_voltage_violation_increment_pu_runtime": ann[
                        "max_storage_target_voltage_violation_increment_pu"
                    ],
                    "max_baseline_target_line_loading_pct_runtime": ann[
                        "max_baseline_target_line_loading_pct"
                    ],
                    "max_baseline_target_line_overload_pct_runtime": ann[
                        "max_baseline_target_line_overload_pct"
                    ],
                    "max_target_line_loading_pct_runtime": ann["max_target_line_loading_pct"],
                    "max_target_line_overload_pct_runtime": ann["max_target_line_overload_pct"],
                    "max_storage_target_line_overload_increment_pct_runtime": ann[
                        "max_storage_target_line_overload_increment_pct"
                    ],
                    "baseline_transformer_violation_hours_runtime": ann["baseline_transformer_violation_hours"],
                    "baseline_hours_with_voltage_violation_runtime": ann["baseline_hours_with_voltage_violation"],
                    "baseline_hours_with_line_overload_runtime": ann["baseline_hours_with_line_overload"],
                    "hours_with_voltage_violation_runtime": ann["hours_with_voltage_violation"],
                    "hours_with_line_overload_runtime": ann["hours_with_line_overload"],
                    "baseline_safety_violation_hours_runtime": ann["baseline_safety_violation_hours"],
                    "storage_safety_violation_hours_runtime": ann["storage_safety_violation_hours"],
                    "delta_safety_violation_hours_runtime": ann["delta_safety_violation_hours"],
                    "baseline_target_hours_with_voltage_violation_runtime": ann[
                        "baseline_target_hours_with_voltage_violation"
                    ],
                    "baseline_target_hours_with_line_overload_runtime": ann[
                        "baseline_target_hours_with_line_overload"
                    ],
                    "target_hours_with_voltage_violation_runtime": ann["target_hours_with_voltage_violation"],
                    "target_hours_with_line_overload_runtime": ann["target_hours_with_line_overload"],
                    "baseline_target_safety_violation_hours_runtime": ann[
                        "baseline_target_safety_violation_hours"
                    ],
                    "target_safety_violation_hours_runtime": ann["target_safety_violation_hours"],
                    "delta_target_safety_violation_hours_runtime": ann["delta_target_safety_violation_hours"],
                }
            )

        return base
