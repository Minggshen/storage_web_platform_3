
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

import numpy as np
import pandas as pd

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.simulation.day_ahead_scheduler import DayAheadScheduler, DayAheadSchedulerConfig
from storage_engine_project.simulation.dispatch_result_models import DayAheadDispatchPlan
from storage_engine_project.simulation.network_constraint_oracle import (
    NetworkConstraintOracle,
    SimpleNetworkConstraintOracle,
    SimpleNetworkOracleConfig,
)
from storage_engine_project.logging_config import get_logger
from storage_engine_project.simulation.rolling_dispatch import (
    RollingDispatchController,
    RollingDispatchConfig,
    RollingDispatchResult,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class AnnualOperationKernelConfig:
    initial_soc: float = 0.50
    use_actual_matrices_for_rolling: bool = True
    monthly_demand_charge_yuan_per_kw: float = 0.0
    annual_start_date: str = "2025-01-01"
    keep_daily_objects: bool = True

    load_round_ndigits: int = 3
    tariff_round_ndigits: int = 4
    compress_fast_proxy_groups: bool = True
    fast_proxy_carry_soc: bool = True

    print_mode_header: bool = True
    print_progress: bool = True
    progress_interval_days: int = 30
    fast_proxy_progress_interval_groups: int = 5
    print_completion_summary: bool = True


@dataclass(slots=True)
class AnnualOperationResult:
    internal_model_id: str
    strategy_id: str
    strategy_name: str

    rated_power_kw: float
    rated_energy_kwh: float
    effective_power_cap_kw: float

    annual_days: int
    hours_per_day: int
    evaluation_mode: str

    plan_charge_kw: np.ndarray
    plan_discharge_kw: np.ndarray
    plan_service_kw: np.ndarray

    exec_charge_kw: np.ndarray
    exec_discharge_kw: np.ndarray
    exec_service_kw: np.ndarray

    baseline_net_load_kw: np.ndarray
    actual_net_load_kw: np.ndarray
    grid_exchange_kw: np.ndarray

    tariff_yuan_per_kwh: np.ndarray
    soc_daily_open: np.ndarray
    soc_daily_close: np.ndarray
    soc_hourly_path: np.ndarray

    arbitrage_revenue_yuan: np.ndarray
    service_capacity_revenue_yuan: np.ndarray
    service_delivery_revenue_yuan: np.ndarray
    service_penalty_yuan: np.ndarray
    degradation_cost_yuan: np.ndarray
    transformer_penalty_yuan: np.ndarray
    voltage_penalty_yuan: np.ndarray

    transformer_slack_kw: np.ndarray
    monthly_demand_saving_yuan: np.ndarray

    annual_arbitrage_revenue_yuan: float
    annual_service_capacity_revenue_yuan: float
    annual_service_delivery_revenue_yuan: float
    annual_service_penalty_yuan: float
    annual_degradation_cost_yuan: float
    annual_transformer_penalty_yuan: float
    annual_voltage_penalty_yuan: float
    annual_demand_saving_yuan: float
    annual_net_operating_cashflow_yuan: float

    annual_battery_throughput_kwh: float
    annual_equivalent_full_cycles: float
    transformer_violation_hours: float
    max_transformer_slack_kw: float

    daily_plan_objects: list[DayAheadDispatchPlan] | None = None
    daily_exec_objects: list[RollingDispatchResult] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, shape in [
            ("plan_charge_kw", (365, 24)),
            ("plan_discharge_kw", (365, 24)),
            ("plan_service_kw", (365, 24)),
            ("exec_charge_kw", (365, 24)),
            ("exec_discharge_kw", (365, 24)),
            ("exec_service_kw", (365, 24)),
            ("baseline_net_load_kw", (365, 24)),
            ("actual_net_load_kw", (365, 24)),
            ("grid_exchange_kw", (365, 24)),
            ("tariff_yuan_per_kwh", (365, 24)),
            ("arbitrage_revenue_yuan", (365, 24)),
            ("service_capacity_revenue_yuan", (365, 24)),
            ("service_delivery_revenue_yuan", (365, 24)),
            ("service_penalty_yuan", (365, 24)),
            ("degradation_cost_yuan", (365, 24)),
            ("transformer_penalty_yuan", (365, 24)),
            ("voltage_penalty_yuan", (365, 24)),
            ("transformer_slack_kw", (365, 24)),
            ("soc_hourly_path", (365, 25)),
        ]:
            arr = np.asarray(getattr(self, name), dtype=float)
            if arr.shape != shape:
                raise ValueError(f"{name} 形状必须为 {shape}，当前为 {arr.shape}")
            setattr(self, name, arr)

        for name, length in [
            ("soc_daily_open", 365),
            ("soc_daily_close", 365),
            ("monthly_demand_saving_yuan", 12),
        ]:
            arr = np.asarray(getattr(self, name), dtype=float).reshape(-1)
            if arr.shape[0] != length:
                raise ValueError(f"{name} 长度必须为 {length}，当前为 {arr.shape[0]}")
            setattr(self, name, arr)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "internal_model_id": self.internal_model_id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "rated_power_kw": self.rated_power_kw,
            "rated_energy_kwh": self.rated_energy_kwh,
            "effective_power_cap_kw": self.effective_power_cap_kw,
            "evaluation_mode": self.evaluation_mode,
            "annual_arbitrage_revenue_yuan": self.annual_arbitrage_revenue_yuan,
            "annual_service_capacity_revenue_yuan": self.annual_service_capacity_revenue_yuan,
            "annual_service_delivery_revenue_yuan": self.annual_service_delivery_revenue_yuan,
            "annual_service_penalty_yuan": self.annual_service_penalty_yuan,
            "annual_degradation_cost_yuan": self.annual_degradation_cost_yuan,
            "annual_transformer_penalty_yuan": self.annual_transformer_penalty_yuan,
            "annual_voltage_penalty_yuan": self.annual_voltage_penalty_yuan,
            "annual_demand_saving_yuan": self.annual_demand_saving_yuan,
            "annual_capacity_revenue_yuan": float(self.metadata.get("annual_capacity_revenue_yuan", 0.0)),
            "annual_loss_reduction_revenue_yuan": float(self.metadata.get("annual_loss_reduction_revenue_yuan", 0.0)),
            "annual_net_operating_cashflow_yuan": self.annual_net_operating_cashflow_yuan,
            "annual_net_operating_cashflow_with_external_revenues_yuan": float(
                self.annual_net_operating_cashflow_yuan
                + float(self.metadata.get("annual_capacity_revenue_yuan", 0.0))
                + float(self.metadata.get("annual_loss_reduction_revenue_yuan", 0.0))
            ),
            "max_voltage_violation_pu": float(self.metadata.get("max_voltage_violation_pu", 0.0)),
            "max_baseline_voltage_violation_pu": float(self.metadata.get("max_baseline_voltage_violation_pu", 0.0)),
            "max_storage_voltage_violation_increment_pu": float(
                self.metadata.get("max_storage_voltage_violation_increment_pu", 0.0)
            ),
            "max_line_loading_pct": float(self.metadata.get("max_line_loading_pct", 0.0)),
            "max_line_overload_pct": float(self.metadata.get("max_line_overload_pct", 0.0)),
            "max_baseline_line_loading_pct": float(self.metadata.get("max_baseline_line_loading_pct", 0.0)),
            "max_baseline_line_overload_pct": float(self.metadata.get("max_baseline_line_overload_pct", 0.0)),
            "max_baseline_target_voltage_violation_pu": float(
                self.metadata.get("max_baseline_target_voltage_violation_pu", 0.0)
            ),
            "max_target_voltage_violation_pu": float(self.metadata.get("max_target_voltage_violation_pu", 0.0)),
            "max_storage_target_voltage_violation_increment_pu": float(
                self.metadata.get("max_storage_target_voltage_violation_increment_pu", 0.0)
            ),
            "max_baseline_target_line_loading_pct": float(
                self.metadata.get("max_baseline_target_line_loading_pct", 0.0)
            ),
            "max_baseline_target_line_overload_pct": float(
                self.metadata.get("max_baseline_target_line_overload_pct", 0.0)
            ),
            "max_target_line_loading_pct": float(self.metadata.get("max_target_line_loading_pct", 0.0)),
            "max_target_line_overload_pct": float(self.metadata.get("max_target_line_overload_pct", 0.0)),
            "max_storage_target_line_overload_increment_pct": float(
                self.metadata.get("max_storage_target_line_overload_increment_pct", 0.0)
            ),
            "baseline_transformer_violation_hours": float(
                self.metadata.get("baseline_transformer_violation_hours", 0.0)
            ),
            "baseline_hours_with_voltage_violation": float(
                self.metadata.get("baseline_hours_with_voltage_violation", 0.0)
            ),
            "baseline_hours_with_line_overload": float(self.metadata.get("baseline_hours_with_line_overload", 0.0)),
            "hours_with_voltage_violation": float(self.metadata.get("hours_with_voltage_violation", 0.0)),
            "hours_with_line_overload": float(self.metadata.get("hours_with_line_overload", 0.0)),
            "baseline_safety_violation_hours": float(self.metadata.get("baseline_safety_violation_hours", 0.0)),
            "storage_safety_violation_hours": float(self.metadata.get("storage_safety_violation_hours", 0.0)),
            "delta_safety_violation_hours": float(self.metadata.get("delta_safety_violation_hours", 0.0)),
            "baseline_target_hours_with_voltage_violation": float(
                self.metadata.get("baseline_target_hours_with_voltage_violation", 0.0)
            ),
            "baseline_target_hours_with_line_overload": float(
                self.metadata.get("baseline_target_hours_with_line_overload", 0.0)
            ),
            "target_hours_with_voltage_violation": float(self.metadata.get("target_hours_with_voltage_violation", 0.0)),
            "target_hours_with_line_overload": float(self.metadata.get("target_hours_with_line_overload", 0.0)),
            "baseline_target_safety_violation_hours": float(
                self.metadata.get("baseline_target_safety_violation_hours", 0.0)
            ),
            "target_safety_violation_hours": float(self.metadata.get("target_safety_violation_hours", 0.0)),
            "delta_target_safety_violation_hours": float(
                self.metadata.get("delta_target_safety_violation_hours", 0.0)
            ),
            "annual_battery_throughput_kwh": self.annual_battery_throughput_kwh,
            "annual_equivalent_full_cycles": self.annual_equivalent_full_cycles,
            "transformer_violation_hours": self.transformer_violation_hours,
            "max_transformer_slack_kw": self.max_transformer_slack_kw,
            "soc_start": float(self.soc_daily_open[0]),
            "soc_end": float(self.soc_daily_close[-1]),
            "soc_terminal_drift": float(self.soc_daily_close[-1] - self.soc_daily_open[0]),
        }

    def monthly_summary_dataframe(self) -> pd.DataFrame:
        dates = pd.date_range(self.metadata.get("annual_start_date", "2025-01-01"), periods=365, freq="D")
        month_idx = dates.month.values
        monthly_capacity = self._monthly_metadata_array("monthly_capacity_revenue_yuan")
        monthly_loss = self._monthly_metadata_array("monthly_loss_reduction_revenue_yuan")
        rows: list[dict[str, Any]] = []
        for m in range(1, 13):
            mask = month_idx == m
            capacity_revenue = float(monthly_capacity[m - 1])
            loss_reduction_revenue = float(monthly_loss[m - 1])
            rows.append(
                {
                    "month": m,
                    "arbitrage_revenue_yuan": float(np.sum(self.arbitrage_revenue_yuan[mask])),
                    "service_capacity_revenue_yuan": float(np.sum(self.service_capacity_revenue_yuan[mask])),
                    "service_delivery_revenue_yuan": float(np.sum(self.service_delivery_revenue_yuan[mask])),
                    "service_penalty_yuan": float(np.sum(self.service_penalty_yuan[mask])),
                    "capacity_revenue_yuan": capacity_revenue,
                    "loss_reduction_revenue_yuan": loss_reduction_revenue,
                    "degradation_cost_yuan": float(np.sum(self.degradation_cost_yuan[mask])),
                    "transformer_penalty_yuan": float(np.sum(self.transformer_penalty_yuan[mask])),
                    "voltage_penalty_yuan": float(np.sum(self.voltage_penalty_yuan[mask])),
                    "demand_saving_yuan": float(self.monthly_demand_saving_yuan[m - 1]),
                    "net_operating_cashflow_yuan": float(
                        np.sum(self.arbitrage_revenue_yuan[mask])
                        + np.sum(self.service_capacity_revenue_yuan[mask])
                        + np.sum(self.service_delivery_revenue_yuan[mask])
                        - np.sum(self.service_penalty_yuan[mask])
                        - np.sum(self.degradation_cost_yuan[mask])
                        - np.sum(self.transformer_penalty_yuan[mask])
                        - np.sum(self.voltage_penalty_yuan[mask])
                        + self.monthly_demand_saving_yuan[m - 1]
                        + capacity_revenue
                        + loss_reduction_revenue
                    ),
                }
            )
        return pd.DataFrame(rows)

    def _monthly_metadata_array(self, key: str) -> np.ndarray:
        value = self.metadata.get(key, None)
        try:
            arr = np.asarray(value, dtype=float).reshape(-1)
        except Exception:
            arr = np.zeros(12, dtype=float)
        if arr.shape[0] != 12:
            return np.zeros(12, dtype=float)
        return arr


class AnnualOperationKernel:
    def __init__(
        self,
        scheduler: DayAheadScheduler | None = None,
        rolling_controller: RollingDispatchController | None = None,
        config: AnnualOperationKernelConfig | None = None,
    ) -> None:
        self.scheduler = scheduler or DayAheadScheduler(DayAheadSchedulerConfig())
        self.rolling_controller = rolling_controller or RollingDispatchController(RollingDispatchConfig())
        self.config = config or AnnualOperationKernelConfig()

    def run_year(
        self,
        ctx: AnnualOperationContext,
        rated_power_kw: float,
        rated_energy_kwh: float,
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: NetworkConstraintOracle | None = None,
        evaluation_mode: str = "full_year",
        fast_proxy_day_stride: int = 14,
        fast_proxy_selected_day_indices: Iterable[int] = tuple(),
        keep_daily_objects: bool | None = None,
    ) -> AnnualOperationResult:
        cfg = self.config
        strategy = ctx.strategy
        evaluation_mode = str(evaluation_mode).strip().lower()

        oracle = network_oracle or SimpleNetworkConstraintOracle(SimpleNetworkOracleConfig())
        load_matrix = np.asarray(actual_load_matrix_kw, dtype=float) if actual_load_matrix_kw is not None else np.asarray(ctx.load_matrix_kw, dtype=float)
        pv_matrix = np.asarray(actual_pv_matrix_kw, dtype=float) if actual_pv_matrix_kw is not None else np.asarray(ctx.pv_matrix_kw, dtype=float)
        tariff = np.asarray(ctx.tariff_matrix_yuan_per_kwh, dtype=float)
        baseline_net = np.asarray(ctx.net_load_matrix_kw, dtype=float)
        actual_net = load_matrix - pv_matrix

        if load_matrix.shape != (365, 24):
            raise ValueError(f"actual_load_matrix_kw 形状必须为 (365, 24)，当前为 {load_matrix.shape}")
        if pv_matrix.shape != (365, 24):
            raise ValueError(f"actual_pv_matrix_kw 形状必须为 (365, 24)，当前为 {pv_matrix.shape}")

        if cfg.print_mode_header:
            logger.info(
                "年度运行模式 evaluation_mode=%s, strategy=%s, P=%.2f, E=%.2f",
                evaluation_mode, strategy.strategy_id, rated_power_kw, rated_energy_kwh,
            )

        if evaluation_mode == "fast_proxy":
            groups = self._build_representative_day_groups(
                load_matrix,
                tariff,
                fast_proxy_day_stride,
                fast_proxy_selected_day_indices,
            )
            representative_days = [rep_day for rep_day, _ in groups]
            if cfg.print_progress:
                logger.info(
                    "年度运行模式 representative_day_count=%s, first_days=%s",
                    len(representative_days), representative_days[:10],
                )
        else:
            groups = [(day, [day]) for day in range(365)]

        dispatch_ctx = ctx
        if evaluation_mode != "fast_proxy":
            dispatch_ctx = replace(
                ctx,
                operation_config=replace(
                    ctx.operation_config,
                    terminal_soc_mode="free",
                    enforce_daily_terminal_soc=False,
                    enable_terminal_soc_correction=False,
                ),
            )

        if keep_daily_objects is None:
            keep_daily_objects = cfg.keep_daily_objects and evaluation_mode != "fast_proxy"

        plan_charge = np.zeros((365, 24), dtype=float)
        plan_discharge = np.zeros((365, 24), dtype=float)
        plan_service = np.zeros((365, 24), dtype=float)
        exec_charge = np.zeros((365, 24), dtype=float)
        exec_discharge = np.zeros((365, 24), dtype=float)
        exec_service = np.zeros((365, 24), dtype=float)
        grid_exchange = np.zeros((365, 24), dtype=float)
        soc_open = np.zeros(365, dtype=float)
        soc_close = np.zeros(365, dtype=float)
        soc_path = np.zeros((365, 25), dtype=float)
        arb = np.zeros((365, 24), dtype=float)
        srv_cap = np.zeros((365, 24), dtype=float)
        srv_del = np.zeros((365, 24), dtype=float)
        srv_pen = np.zeros((365, 24), dtype=float)
        deg = np.zeros((365, 24), dtype=float)
        tr_pen = np.zeros((365, 24), dtype=float)
        v_pen = np.zeros((365, 24), dtype=float)
        slack = np.zeros((365, 24), dtype=float)

        daily_plans: list[DayAheadDispatchPlan] = []
        daily_execs: list[RollingDispatchResult] = []

        current_soc = float(np.clip(cfg.initial_soc, 0.0, 1.0))
        soc_correction_errors: list[float] = []
        max_voltage_violation_pu = 0.0
        max_baseline_voltage_violation_pu = 0.0
        max_storage_voltage_violation_increment_pu = 0.0
        max_line_loading_pct = 0.0
        max_line_overload_pct = 0.0
        max_baseline_line_loading_pct = 0.0
        max_baseline_line_overload_pct = 0.0
        baseline_hours_with_voltage_violation = 0.0
        baseline_hours_with_line_overload = 0.0
        hours_with_voltage_violation = 0.0
        hours_with_line_overload = 0.0
        max_baseline_target_voltage_violation_pu = 0.0
        max_target_voltage_violation_pu = 0.0
        max_storage_target_voltage_violation_increment_pu = 0.0
        max_baseline_target_line_loading_pct = 0.0
        max_baseline_target_line_overload_pct = 0.0
        max_target_line_loading_pct = 0.0
        max_target_line_overload_pct = 0.0
        max_storage_target_line_overload_increment_pct = 0.0
        baseline_target_hours_with_voltage_violation = 0.0
        baseline_target_hours_with_line_overload = 0.0
        target_hours_with_voltage_violation = 0.0
        target_hours_with_line_overload = 0.0

        for idx, (rep_day, covered_days) in enumerate(groups, start=1):
            if evaluation_mode == "fast_proxy":
                rep_initial_soc = current_soc if cfg.fast_proxy_carry_soc else float(np.clip(cfg.initial_soc, 0.0, 1.0))
                if cfg.print_progress and (
                    idx == 1
                    or idx == len(groups)
                    or idx % max(1, int(cfg.fast_proxy_progress_interval_groups)) == 0
                ):
                    logger.info(
                        "年度运行 代表日 %s/%s | rep_day=%s | 覆盖天数=%s | 当前日初SOC=%.4f",
                        idx, len(groups), rep_day + 1, len(covered_days), rep_initial_soc,
                    )
            else:
                rep_initial_soc = current_soc
                if cfg.print_progress and (
                    idx == 1
                    or idx == len(groups)
                    or idx % max(1, int(cfg.progress_interval_days)) == 0
                ):
                    logger.info(
                        "年度运行 进度 %s/365 | 当前日初SOC=%.4f | 策略=%s",
                        idx, rep_initial_soc, strategy.strategy_id,
                    )

            plan = self.scheduler.schedule_day(
                ctx=dispatch_ctx,
                day_index=rep_day,
                rated_power_kw=float(rated_power_kw),
                rated_energy_kwh=float(rated_energy_kwh),
                initial_soc=rep_initial_soc,
            )
            exec_result = self.rolling_controller.execute_day(
                ctx=dispatch_ctx,
                plan=plan,
                network_oracle=oracle,
                actual_load_kw=load_matrix[rep_day],
                actual_pv_kw=pv_matrix[rep_day],
            )

            current_soc = float(exec_result.final_soc)
            terminal_soc_error = exec_result.metadata.get("terminal_soc_error_after_correction")
            if terminal_soc_error is not None:
                soc_correction_errors.append(float(terminal_soc_error))
            covered_day_count = max(1, len(covered_days))
            for trace in exec_result.network_trace:
                if not isinstance(trace, dict):
                    continue
                baseline_voltage_violation = self._to_nonnegative_float(trace.get("baseline_voltage_violation_pu"))
                voltage_violation = self._to_nonnegative_float(trace.get("voltage_violation_pu"))
                storage_incremental_violation = self._to_nonnegative_float(trace.get("storage_voltage_violation_increment_pu"))
                baseline_line_loading_pct = self._to_nonnegative_float(trace.get("baseline_line_loading_max_pct"))
                baseline_line_overload_pct = max(0.0, baseline_line_loading_pct - 100.0)
                line_loading_pct = self._to_nonnegative_float(trace.get("line_loading_max_pct"))
                line_overload_pct = max(0.0, line_loading_pct - 100.0)
                baseline_target_voltage_violation = self._to_nonnegative_float(trace.get("baseline_target_voltage_violation_pu"))
                target_voltage_violation = self._to_nonnegative_float(trace.get("target_voltage_violation_pu"))
                storage_target_incremental_violation = self._to_nonnegative_float(
                    trace.get("storage_target_voltage_violation_increment_pu")
                )
                baseline_target_line_loading_pct = self._to_nonnegative_float(
                    trace.get("baseline_target_line_loading_max_pct")
                )
                baseline_target_line_overload_pct = self._to_nonnegative_float(
                    trace.get("baseline_target_line_overload_pct")
                )
                target_line_loading_pct = self._to_nonnegative_float(trace.get("target_line_loading_max_pct"))
                target_line_overload_pct = self._to_nonnegative_float(trace.get("target_line_overload_pct"))
                storage_target_line_overload_increment_pct = self._to_nonnegative_float(
                    trace.get("storage_target_line_overload_increment_pct")
                )

                max_baseline_voltage_violation_pu = max(max_baseline_voltage_violation_pu, baseline_voltage_violation)
                max_voltage_violation_pu = max(max_voltage_violation_pu, voltage_violation)
                max_storage_voltage_violation_increment_pu = max(
                    max_storage_voltage_violation_increment_pu,
                    storage_incremental_violation,
                )
                max_baseline_line_loading_pct = max(max_baseline_line_loading_pct, baseline_line_loading_pct)
                max_baseline_line_overload_pct = max(max_baseline_line_overload_pct, baseline_line_overload_pct)
                max_line_loading_pct = max(max_line_loading_pct, line_loading_pct)
                max_line_overload_pct = max(max_line_overload_pct, line_overload_pct)
                max_baseline_target_voltage_violation_pu = max(
                    max_baseline_target_voltage_violation_pu,
                    baseline_target_voltage_violation,
                )
                max_target_voltage_violation_pu = max(max_target_voltage_violation_pu, target_voltage_violation)
                max_storage_target_voltage_violation_increment_pu = max(
                    max_storage_target_voltage_violation_increment_pu,
                    storage_target_incremental_violation,
                )
                max_baseline_target_line_loading_pct = max(
                    max_baseline_target_line_loading_pct,
                    baseline_target_line_loading_pct,
                )
                max_baseline_target_line_overload_pct = max(
                    max_baseline_target_line_overload_pct,
                    baseline_target_line_overload_pct,
                )
                max_target_line_loading_pct = max(max_target_line_loading_pct, target_line_loading_pct)
                max_target_line_overload_pct = max(max_target_line_overload_pct, target_line_overload_pct)
                max_storage_target_line_overload_increment_pct = max(
                    max_storage_target_line_overload_increment_pct,
                    storage_target_line_overload_increment_pct,
                )

                if baseline_voltage_violation > 1e-9:
                    baseline_hours_with_voltage_violation += float(covered_day_count)
                if baseline_line_overload_pct > 1e-9:
                    baseline_hours_with_line_overload += float(covered_day_count)
                if voltage_violation > 1e-9:
                    hours_with_voltage_violation += float(covered_day_count)
                if line_overload_pct > 1e-9:
                    hours_with_line_overload += float(covered_day_count)
                if baseline_target_voltage_violation > 1e-9:
                    baseline_target_hours_with_voltage_violation += float(covered_day_count)
                if baseline_target_line_overload_pct > 1e-9:
                    baseline_target_hours_with_line_overload += float(covered_day_count)
                if target_voltage_violation > 1e-9:
                    target_hours_with_voltage_violation += float(covered_day_count)
                if target_line_overload_pct > 1e-9:
                    target_hours_with_line_overload += float(covered_day_count)

            for day in covered_days:
                soc_open[day] = rep_initial_soc
                soc_close[day] = float(exec_result.final_soc)
                plan_charge[day] = plan.charge_kw
                plan_discharge[day] = plan.discharge_kw
                plan_service[day] = plan.service_commit_kw
                exec_charge[day] = exec_result.executed_charge_kw
                exec_discharge[day] = exec_result.executed_discharge_kw
                exec_service[day] = exec_result.executed_service_kw
                grid_exchange[day] = exec_result.grid_exchange_kw
                soc_path[day] = exec_result.soc_path
                arb[day] = exec_result.arbitrage_revenue_yuan_by_hour
                srv_cap[day] = exec_result.service_capacity_revenue_yuan_by_hour
                srv_del[day] = exec_result.service_delivery_revenue_yuan_by_hour
                srv_pen[day] = exec_result.service_penalty_yuan_by_hour
                deg[day] = exec_result.degradation_cost_yuan_by_hour
                tr_pen[day] = exec_result.transformer_penalty_yuan_by_hour
                v_pen[day] = exec_result.voltage_penalty_yuan_by_hour
                slack[day] = exec_result.transformer_slack_kw

            if keep_daily_objects:
                daily_plans.append(plan)
                daily_execs.append(exec_result)

        monthly_demand_saving = self._compute_monthly_demand_saving(
            baseline_net_load_kw=baseline_net,
            actual_grid_exchange_kw=grid_exchange,
            monthly_demand_charge_yuan_per_kw=float(cfg.monthly_demand_charge_yuan_per_kw),
            annual_start_date=cfg.annual_start_date,
        )

        annual_arbitrage = float(np.sum(arb))
        annual_service_cap = float(np.sum(srv_cap))
        annual_service_del = float(np.sum(srv_del))
        annual_service_pen = float(np.sum(srv_pen))
        annual_deg = float(np.sum(deg))
        annual_tr_pen = float(np.sum(tr_pen))
        annual_v_pen = float(np.sum(v_pen))
        annual_demand_saving = float(np.sum(monthly_demand_saving))
        annual_cashflow = (
            annual_arbitrage + annual_service_cap + annual_service_del
            - annual_service_pen - annual_deg - annual_tr_pen - annual_v_pen
            + annual_demand_saving
        )
        annual_throughput = float(np.sum(exec_charge) + np.sum(exec_discharge) + np.sum(exec_service))
        annual_eq_cycles = float(annual_throughput / (2.0 * float(rated_energy_kwh)) if rated_energy_kwh > 0 else 0.0)
        effective_power_cap_kw = float(rated_power_kw) * float(ctx.safety_config.resolve_power_derate(strategy.safety_level))
        transformer_limit = ctx.transformer_active_power_limit_kw
        baseline_transformer_violation_hours = 0.0
        if transformer_limit is not None:
            baseline_transformer_violation_hours = float(np.sum(baseline_net > float(transformer_limit) + 1e-9))
        storage_transformer_violation_hours = float(np.sum(slack > 1e-9))
        baseline_safety_violation_hours = (
            baseline_transformer_violation_hours
            + baseline_hours_with_voltage_violation
            + baseline_hours_with_line_overload
        )
        storage_safety_violation_hours = (
            storage_transformer_violation_hours
            + hours_with_voltage_violation
            + hours_with_line_overload
        )
        delta_safety_violation_hours = baseline_safety_violation_hours - storage_safety_violation_hours
        baseline_target_safety_violation_hours = (
            baseline_transformer_violation_hours
            + baseline_target_hours_with_voltage_violation
            + baseline_target_hours_with_line_overload
        )
        target_safety_violation_hours = (
            storage_transformer_violation_hours
            + target_hours_with_voltage_violation
            + target_hours_with_line_overload
        )
        delta_target_safety_violation_hours = baseline_target_safety_violation_hours - target_safety_violation_hours

        if cfg.print_completion_summary:
            mean_terminal_error = float(np.mean(np.abs(soc_correction_errors))) if soc_correction_errors else 0.0
            logger.info(
                "年度运行完成 mode=%s | annual_cashflow=%.2f | cycles=%.2f | transformer_hours=%.0f | mean_terminal_soc_error=%.4f",
                evaluation_mode, annual_cashflow, annual_eq_cycles, storage_transformer_violation_hours, mean_terminal_error,
            )

        return AnnualOperationResult(
            internal_model_id=ctx.internal_model_id,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.strategy_name,
            rated_power_kw=float(rated_power_kw),
            rated_energy_kwh=float(rated_energy_kwh),
            effective_power_cap_kw=effective_power_cap_kw,
            annual_days=365,
            hours_per_day=24,
            evaluation_mode=evaluation_mode,
            plan_charge_kw=plan_charge,
            plan_discharge_kw=plan_discharge,
            plan_service_kw=plan_service,
            exec_charge_kw=exec_charge,
            exec_discharge_kw=exec_discharge,
            exec_service_kw=exec_service,
            baseline_net_load_kw=baseline_net,
            actual_net_load_kw=actual_net,
            grid_exchange_kw=grid_exchange,
            tariff_yuan_per_kwh=tariff,
            soc_daily_open=soc_open,
            soc_daily_close=soc_close,
            soc_hourly_path=soc_path,
            arbitrage_revenue_yuan=arb,
            service_capacity_revenue_yuan=srv_cap,
            service_delivery_revenue_yuan=srv_del,
            service_penalty_yuan=srv_pen,
            degradation_cost_yuan=deg,
            transformer_penalty_yuan=tr_pen,
            voltage_penalty_yuan=v_pen,
            transformer_slack_kw=slack,
            monthly_demand_saving_yuan=monthly_demand_saving,
            annual_arbitrage_revenue_yuan=annual_arbitrage,
            annual_service_capacity_revenue_yuan=annual_service_cap,
            annual_service_delivery_revenue_yuan=annual_service_del,
            annual_service_penalty_yuan=annual_service_pen,
            annual_degradation_cost_yuan=annual_deg,
            annual_transformer_penalty_yuan=annual_tr_pen,
            annual_voltage_penalty_yuan=annual_v_pen,
            annual_demand_saving_yuan=annual_demand_saving,
            annual_net_operating_cashflow_yuan=annual_cashflow,
            annual_battery_throughput_kwh=annual_throughput,
            annual_equivalent_full_cycles=annual_eq_cycles,
            transformer_violation_hours=storage_transformer_violation_hours,
            max_transformer_slack_kw=float(np.max(slack)) if slack.size else 0.0,
            daily_plan_objects=daily_plans if keep_daily_objects else None,
            daily_exec_objects=daily_execs if keep_daily_objects else None,
            metadata={
                "kernel_initial_soc": cfg.initial_soc,
                "monthly_demand_charge_yuan_per_kw": cfg.monthly_demand_charge_yuan_per_kw,
                "annual_start_date": cfg.annual_start_date,
                "use_actual_matrices_for_rolling": cfg.use_actual_matrices_for_rolling,
                "represented_day_groups": [(rep_day, list(days)) for rep_day, days in groups],
                "representative_day_count": len(groups),
                "fast_proxy_carry_soc": bool(cfg.fast_proxy_carry_soc),
                "strategy_eta_charge": float(strategy.eta_charge),
                "strategy_eta_discharge": float(strategy.eta_discharge),
                "strategy_service_soc_coeff": float(strategy.eta_charge - 1.0 / strategy.eta_discharge),
                "mean_terminal_soc_error": float(np.mean(np.abs(soc_correction_errors))) if soc_correction_errors else 0.0,
                "max_terminal_soc_error": float(np.max(np.abs(soc_correction_errors))) if soc_correction_errors else 0.0,
                "max_voltage_violation_pu": float(max_voltage_violation_pu),
                "max_baseline_voltage_violation_pu": float(max_baseline_voltage_violation_pu),
                "max_storage_voltage_violation_increment_pu": float(max_storage_voltage_violation_increment_pu),
                "max_line_loading_pct": float(max_line_loading_pct),
                "max_line_overload_pct": float(max_line_overload_pct),
                "max_baseline_line_loading_pct": float(max_baseline_line_loading_pct),
                "max_baseline_line_overload_pct": float(max_baseline_line_overload_pct),
                "max_baseline_target_voltage_violation_pu": float(max_baseline_target_voltage_violation_pu),
                "max_target_voltage_violation_pu": float(max_target_voltage_violation_pu),
                "max_storage_target_voltage_violation_increment_pu": float(
                    max_storage_target_voltage_violation_increment_pu
                ),
                "max_baseline_target_line_loading_pct": float(max_baseline_target_line_loading_pct),
                "max_baseline_target_line_overload_pct": float(max_baseline_target_line_overload_pct),
                "max_target_line_loading_pct": float(max_target_line_loading_pct),
                "max_target_line_overload_pct": float(max_target_line_overload_pct),
                "max_storage_target_line_overload_increment_pct": float(max_storage_target_line_overload_increment_pct),
                "baseline_transformer_violation_hours": float(baseline_transformer_violation_hours),
                "baseline_hours_with_voltage_violation": float(baseline_hours_with_voltage_violation),
                "baseline_hours_with_line_overload": float(baseline_hours_with_line_overload),
                "hours_with_voltage_violation": float(hours_with_voltage_violation),
                "hours_with_line_overload": float(hours_with_line_overload),
                "baseline_safety_violation_hours": float(baseline_safety_violation_hours),
                "storage_safety_violation_hours": float(storage_safety_violation_hours),
                "delta_safety_violation_hours": float(delta_safety_violation_hours),
                "baseline_target_hours_with_voltage_violation": float(baseline_target_hours_with_voltage_violation),
                "baseline_target_hours_with_line_overload": float(baseline_target_hours_with_line_overload),
                "target_hours_with_voltage_violation": float(target_hours_with_voltage_violation),
                "target_hours_with_line_overload": float(target_hours_with_line_overload),
                "baseline_target_safety_violation_hours": float(baseline_target_safety_violation_hours),
                "target_safety_violation_hours": float(target_safety_violation_hours),
                "delta_target_safety_violation_hours": float(delta_target_safety_violation_hours),
            },
        )

    @staticmethod
    def _to_nonnegative_float(value: Any) -> float:
        try:
            if value in (None, ""):
                return 0.0
            parsed = float(value)
        except Exception:
            return 0.0
        if not np.isfinite(parsed):
            return 0.0
        return max(0.0, float(parsed))

    def _build_representative_day_groups(
        self,
        load_matrix_kw: np.ndarray,
        tariff_matrix_yuan_per_kwh: np.ndarray,
        fast_proxy_day_stride: int,
        fast_proxy_selected_day_indices: Iterable[int],
    ) -> list[tuple[int, list[int]]]:
        if fast_proxy_selected_day_indices:
            selected = sorted({int(x) for x in fast_proxy_selected_day_indices if 0 <= int(x) < 365})
            return [(d, [d]) for d in selected]

        groups: dict[tuple[tuple[float, ...], tuple[float, ...]], list[int]] = defaultdict(list)
        for day in range(365):
            sig = (
                tuple(np.round(np.asarray(load_matrix_kw[day], dtype=float), self.config.load_round_ndigits)),
                tuple(np.round(np.asarray(tariff_matrix_yuan_per_kwh[day], dtype=float), self.config.tariff_round_ndigits)),
            )
            groups[sig].append(day)

        rep_groups: list[tuple[int, list[int]]] = []
        for _, days in groups.items():
            days = sorted(days)
            if self.config.compress_fast_proxy_groups:
                rep_groups.append((days[0], days))
            else:
                stride = max(1, int(fast_proxy_day_stride))
                if stride <= 1 or len(days) <= stride:
                    rep_groups.append((days[0], days))
                else:
                    for start in range(0, len(days), stride):
                        chunk = days[start:start + stride]
                        rep_groups.append((chunk[0], chunk))

        rep_groups.sort(key=lambda x: x[0])
        return rep_groups

    @staticmethod
    def _compute_monthly_demand_saving(
        baseline_net_load_kw: np.ndarray,
        actual_grid_exchange_kw: np.ndarray,
        monthly_demand_charge_yuan_per_kw: float,
        annual_start_date: str,
    ) -> np.ndarray:
        out = np.zeros(12, dtype=float)
        if monthly_demand_charge_yuan_per_kw <= 0:
            return out

        dates = pd.date_range(annual_start_date, periods=365, freq="D")
        month_idx = dates.month.values
        baseline_import = np.maximum(np.asarray(baseline_net_load_kw, dtype=float), 0.0)
        actual_import = np.maximum(np.asarray(actual_grid_exchange_kw, dtype=float), 0.0)
        for month in range(1, 13):
            mask = month_idx == month
            if not np.any(mask):
                continue
            baseline_peak = float(np.max(baseline_import[mask]))
            actual_peak = float(np.max(actual_import[mask]))
            reduction_kw = max(0.0, baseline_peak - actual_peak)
            out[month - 1] = reduction_kw * float(monthly_demand_charge_yuan_per_kw)
        return out
