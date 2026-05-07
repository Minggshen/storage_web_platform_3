from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class CapitalCostBreakdown:
    """
    初始投资拆解。
    """

    energy_capex_yuan: float = 0.0
    power_capex_yuan: float = 0.0
    safety_markup_yuan: float = 0.0
    integration_markup_yuan: float = 0.0
    other_capex_yuan: float = 0.0

    @property
    def total_capex_yuan(self) -> float:
        return (
            self.energy_capex_yuan
            + self.power_capex_yuan
            + self.safety_markup_yuan
            + self.integration_markup_yuan
            + self.other_capex_yuan
        )

    def summary_dict(self) -> dict[str, float]:
        return {
            "energy_capex_yuan": float(self.energy_capex_yuan),
            "power_capex_yuan": float(self.power_capex_yuan),
            "safety_markup_yuan": float(self.safety_markup_yuan),
            "integration_markup_yuan": float(self.integration_markup_yuan),
            "other_capex_yuan": float(self.other_capex_yuan),
            "total_capex_yuan": float(self.total_capex_yuan),
        }


@dataclass(slots=True)
class AnnualRevenueAuditResult:
    """
    年度收益审计结果。
    这一层只针对“运行年度”本身，不引入折现和全生命周期。
    """

    internal_model_id: str
    strategy_id: str
    strategy_name: str

    rated_power_kw: float
    rated_energy_kwh: float
    effective_power_cap_kw: float

    annual_arbitrage_revenue_yuan: float
    annual_service_capacity_revenue_yuan: float
    annual_service_delivery_revenue_yuan: float
    annual_service_penalty_yuan: float
    annual_demand_saving_yuan: float
    annual_capacity_revenue_yuan: float
    annual_loss_reduction_revenue_yuan: float

    annual_degradation_cost_yuan: float
    annual_transformer_penalty_yuan: float
    annual_voltage_penalty_yuan: float
    annual_om_cost_yuan: float

    annual_gross_revenue_yuan: float
    annual_service_net_revenue_yuan: float
    annual_operating_cost_yuan: float
    annual_net_operating_cashflow_before_om_yuan: float
    annual_net_operating_cashflow_after_om_yuan: float

    annual_battery_throughput_kwh: float
    annual_equivalent_full_cycles: float
    transformer_violation_hours: float
    max_transformer_slack_kw: float

    monthly_summary: pd.DataFrame | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "internal_model_id": self.internal_model_id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "rated_power_kw": float(self.rated_power_kw),
            "rated_energy_kwh": float(self.rated_energy_kwh),
            "effective_power_cap_kw": float(self.effective_power_cap_kw),
            "annual_arbitrage_revenue_yuan": float(self.annual_arbitrage_revenue_yuan),
            "annual_service_capacity_revenue_yuan": float(self.annual_service_capacity_revenue_yuan),
            "annual_service_delivery_revenue_yuan": float(self.annual_service_delivery_revenue_yuan),
            "annual_service_penalty_yuan": float(self.annual_service_penalty_yuan),
            "annual_auxiliary_service_revenue_yuan": float(
                self.annual_service_capacity_revenue_yuan
                + self.annual_service_delivery_revenue_yuan
                - self.annual_service_penalty_yuan
            ),
            "annual_demand_saving_yuan": float(self.annual_demand_saving_yuan),
            "annual_capacity_revenue_yuan": float(self.annual_capacity_revenue_yuan),
            "annual_loss_reduction_revenue_yuan": float(self.annual_loss_reduction_revenue_yuan),
            "annual_degradation_cost_yuan": float(self.annual_degradation_cost_yuan),
            "annual_transformer_penalty_yuan": float(self.annual_transformer_penalty_yuan),
            "annual_voltage_penalty_yuan": float(self.annual_voltage_penalty_yuan),
            "annual_om_cost_yuan": float(self.annual_om_cost_yuan),
            "annual_gross_revenue_yuan": float(self.annual_gross_revenue_yuan),
            "annual_service_net_revenue_yuan": float(self.annual_service_net_revenue_yuan),
            "annual_operating_cost_yuan": float(self.annual_operating_cost_yuan),
            "annual_net_operating_cashflow_before_om_yuan": float(
                self.annual_net_operating_cashflow_before_om_yuan
            ),
            "annual_net_operating_cashflow_after_om_yuan": float(
                self.annual_net_operating_cashflow_after_om_yuan
            ),
            "annual_battery_throughput_kwh": float(self.annual_battery_throughput_kwh),
            "annual_equivalent_full_cycles": float(self.annual_equivalent_full_cycles),
            "transformer_violation_hours": float(self.transformer_violation_hours),
            "max_transformer_slack_kw": float(self.max_transformer_slack_kw),
        }


@dataclass(slots=True)
class LifecycleCashflowTable:
    """
    生命周期现金流表。
    """

    years: np.ndarray
    revenue_yuan: np.ndarray
    om_cost_yuan: np.ndarray
    replacement_cost_yuan: np.ndarray
    salvage_value_yuan: np.ndarray
    net_cashflow_yuan: np.ndarray
    discounted_net_cashflow_yuan: np.ndarray
    arbitrage_revenue_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    demand_saving_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    auxiliary_service_revenue_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    capacity_revenue_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    loss_reduction_revenue_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    service_penalty_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    degradation_cost_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    network_penalty_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    operating_revenue_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    operating_cost_yuan: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    battery_soh: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    capacity_factor: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))

    def __post_init__(self) -> None:
        required_arrays = [
            "years",
            "revenue_yuan",
            "om_cost_yuan",
            "replacement_cost_yuan",
            "salvage_value_yuan",
            "net_cashflow_yuan",
            "discounted_net_cashflow_yuan",
        ]
        length = None
        for name in required_arrays:
            arr = np.asarray(getattr(self, name), dtype=float).reshape(-1)
            setattr(self, name, arr)
            if length is None:
                length = arr.shape[0]
            elif arr.shape[0] != length:
                raise ValueError(f"{name} 长度与其他现金流列不一致。")

        optional_arrays = [
            "arbitrage_revenue_yuan",
            "demand_saving_yuan",
            "auxiliary_service_revenue_yuan",
            "capacity_revenue_yuan",
            "loss_reduction_revenue_yuan",
            "service_penalty_yuan",
            "degradation_cost_yuan",
            "network_penalty_yuan",
            "operating_revenue_yuan",
            "operating_cost_yuan",
            "battery_soh",
            "capacity_factor",
        ]
        for name in optional_arrays:
            arr = np.asarray(getattr(self, name), dtype=float).reshape(-1)
            if arr.size == 0:
                if name in {"battery_soh", "capacity_factor"}:
                    arr = np.ones(int(length or 0), dtype=float)
                else:
                    arr = np.zeros(int(length or 0), dtype=float)
            if arr.shape[0] != length:
                raise ValueError(f"{name} 长度与其他现金流列不一致。")
            setattr(self, name, arr)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "year": self.years,
                "revenue_yuan": self.revenue_yuan,
                "arbitrage_revenue_yuan": self.arbitrage_revenue_yuan,
                "demand_saving_yuan": self.demand_saving_yuan,
                "auxiliary_service_revenue_yuan": self.auxiliary_service_revenue_yuan,
                "capacity_revenue_yuan": self.capacity_revenue_yuan,
                "loss_reduction_revenue_yuan": self.loss_reduction_revenue_yuan,
                "service_penalty_yuan": self.service_penalty_yuan,
                "degradation_cost_yuan": self.degradation_cost_yuan,
                "network_penalty_yuan": self.network_penalty_yuan,
                "operating_revenue_yuan": self.operating_revenue_yuan,
                "operating_cost_yuan": self.operating_cost_yuan,
                "battery_soh": self.battery_soh,
                "capacity_factor": self.capacity_factor,
                "om_cost_yuan": self.om_cost_yuan,
                "replacement_cost_yuan": self.replacement_cost_yuan,
                "salvage_value_yuan": self.salvage_value_yuan,
                "net_cashflow_yuan": self.net_cashflow_yuan,
                "discounted_net_cashflow_yuan": self.discounted_net_cashflow_yuan,
            }
        )


@dataclass(slots=True)
class LifecycleFinancialResult:
    """
    生命周期财务结果。
    """

    internal_model_id: str
    strategy_id: str
    strategy_name: str

    rated_power_kw: float
    rated_energy_kwh: float

    project_life_years: int
    discount_rate: float

    capital_cost_breakdown: CapitalCostBreakdown
    annual_revenue_audit: AnnualRevenueAuditResult
    cashflow_table: LifecycleCashflowTable

    initial_investment_yuan: float
    total_replacement_cost_yuan: float
    total_salvage_value_yuan: float

    npv_yuan: float
    irr: float | None
    simple_payback_years: float | None
    discounted_payback_years: float | None

    annualized_net_cashflow_yuan: float
    lc_net_profit_yuan: float

    metadata: dict[str, Any] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "internal_model_id": self.internal_model_id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "rated_power_kw": float(self.rated_power_kw),
            "rated_energy_kwh": float(self.rated_energy_kwh),
            "project_life_years": int(self.project_life_years),
            "discount_rate": float(self.discount_rate),
            "initial_investment_yuan": float(self.initial_investment_yuan),
            "gross_initial_investment_yuan": float(self.metadata.get("gross_initial_investment_yuan", self.initial_investment_yuan)),
            "government_subsidy_yuan": float(self.metadata.get("government_subsidy_yuan", 0.0)),
            "initial_net_investment_yuan": float(self.metadata.get("initial_net_investment_yuan", self.initial_investment_yuan)),
            "total_replacement_cost_yuan": float(self.total_replacement_cost_yuan),
            "total_salvage_value_yuan": float(self.total_salvage_value_yuan),
            "annual_replacement_equivalent_cost_yuan": float(
                self.metadata.get("annual_replacement_equivalent_cost_yuan", 0.0)
            ),
            "replacement_year_effective": self.metadata.get("replacement_year_effective"),
            "cycle_life_efc_effective": float(self.metadata.get("cycle_life_efc_effective", 0.0)),
            "replacement_trigger_soh_effective": float(self.metadata.get("replacement_trigger_soh_effective", 0.0)),
            "replacement_reset_soh_effective": float(self.metadata.get("replacement_reset_soh_effective", 0.0)),
            "first_year_capacity_factor": float(self.metadata.get("first_year_capacity_factor", 1.0)),
            "last_year_capacity_factor": float(self.metadata.get("last_year_capacity_factor", 1.0)),
            "annual_salvage_equivalent_value_yuan": float(
                self.metadata.get("annual_salvage_equivalent_value_yuan", 0.0)
            ),
            "annual_net_cashflow_after_replacement_equivalent_yuan": float(
                self.metadata.get("annual_net_cashflow_after_replacement_equivalent_yuan", self.annualized_net_cashflow_yuan)
            ),
            "npv_yuan": float(self.npv_yuan),
            "irr": None if self.irr is None else float(self.irr),
            "simple_payback_years": None if self.simple_payback_years is None else float(self.simple_payback_years),
            "discounted_payback_years": None if self.discounted_payback_years is None else float(self.discounted_payback_years),
            "annualized_net_cashflow_yuan": float(self.annualized_net_cashflow_yuan),
            "lc_net_profit_yuan": float(self.lc_net_profit_yuan),
            **self.capital_cost_breakdown.summary_dict(),
            **self.annual_revenue_audit.summary_dict(),
        }

    def cashflow_dataframe(self) -> pd.DataFrame:
        return self.cashflow_table.to_dataframe()
