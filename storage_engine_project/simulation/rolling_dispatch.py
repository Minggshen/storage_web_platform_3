from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.simulation.dispatch_result_models import DayAheadDispatchPlan
from storage_engine_project.simulation.network_constraint_oracle import (
    NetworkConstraintOracle,
    SimpleNetworkConstraintOracle,
)


def _to_1d(arr: np.ndarray | list[float], length: int, name: str) -> np.ndarray:
    out = np.asarray(arr, dtype=float).reshape(-1)
    if out.shape[0] != length:
        raise ValueError(f"{name} 长度必须为 {length}，当前为 {out.shape[0]}")
    return out


@dataclass(slots=True)
class RollingDispatchConfig:
    transformer_violation_penalty_yuan_per_kwh: float = 300.0
    degradation_weight_service: float = 1.0
    allow_service_curtailment: bool = True
    safety_first: bool = True
    enforce_soc_hard_clip: bool = True
    net_power_execution_mode: bool = True

    enable_terminal_soc_correction: bool = True
    terminal_soc_correction_hours: int = 4
    terminal_soc_correction_max_fraction_of_power: float = 0.70
    terminal_soc_correction_tolerance_override: float | None = None


@dataclass(slots=True)
class RollingDispatchResult:
    day_index: int
    internal_model_id: str
    strategy_id: str
    initial_soc: float
    final_soc: float
    hour_count: int
    actual_load_kw: np.ndarray
    actual_pv_kw: np.ndarray
    actual_net_load_kw: np.ndarray
    tariff_yuan_per_kwh: np.ndarray
    planned_charge_kw: np.ndarray
    planned_discharge_kw: np.ndarray
    planned_service_kw: np.ndarray
    executed_charge_kw: np.ndarray
    executed_discharge_kw: np.ndarray
    executed_service_kw: np.ndarray
    grid_exchange_kw: np.ndarray
    transformer_slack_kw: np.ndarray
    voltage_penalty_yuan_by_hour: np.ndarray
    soc_path: np.ndarray
    arbitrage_revenue_yuan_by_hour: np.ndarray
    service_capacity_revenue_yuan_by_hour: np.ndarray
    service_delivery_revenue_yuan_by_hour: np.ndarray
    service_penalty_yuan_by_hour: np.ndarray
    degradation_cost_yuan_by_hour: np.ndarray
    transformer_penalty_yuan_by_hour: np.ndarray
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    network_trace: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        h = int(self.hour_count)
        for name in [
            "actual_load_kw","actual_pv_kw","actual_net_load_kw","tariff_yuan_per_kwh",
            "planned_charge_kw","planned_discharge_kw","planned_service_kw",
            "executed_charge_kw","executed_discharge_kw","executed_service_kw",
            "grid_exchange_kw","transformer_slack_kw","voltage_penalty_yuan_by_hour",
            "arbitrage_revenue_yuan_by_hour","service_capacity_revenue_yuan_by_hour",
            "service_delivery_revenue_yuan_by_hour","service_penalty_yuan_by_hour",
            "degradation_cost_yuan_by_hour","transformer_penalty_yuan_by_hour",
        ]:
            setattr(self, name, _to_1d(getattr(self, name), h, name))
        self.soc_path = _to_1d(self.soc_path, h + 1, "soc_path")


class RollingDispatchController:
    def __init__(self, config: RollingDispatchConfig | None = None) -> None:
        self.config = config or RollingDispatchConfig()

    def execute_day(
        self,
        ctx: AnnualOperationContext,
        plan: DayAheadDispatchPlan,
        network_oracle: NetworkConstraintOracle | None = None,
        actual_load_kw: np.ndarray | None = None,
        actual_pv_kw: np.ndarray | None = None,
    ) -> RollingDispatchResult:
        oracle = network_oracle or SimpleNetworkConstraintOracle()
        cfg = self.config
        h = 24

        strategy = ctx.strategy
        eta_c = float(strategy.eta_charge)
        eta_d = float(strategy.eta_discharge)
        rated_energy_kwh = float(plan.rated_energy_kwh)
        eff_power_cap = float(plan.effective_power_cap_kw)

        actual_load = (
            np.asarray(actual_load_kw, dtype=float).reshape(24)
            if actual_load_kw is not None
            else np.asarray(plan.load_kw, dtype=float).reshape(24)
        )
        actual_pv = (
            np.asarray(actual_pv_kw, dtype=float).reshape(24)
            if actual_pv_kw is not None
            else np.asarray(plan.pv_kw, dtype=float).reshape(24)
        )
        actual_net = actual_load - actual_pv

        pch_plan = np.asarray(plan.charge_kw, dtype=float).reshape(24)
        pdis_plan = np.asarray(plan.discharge_kw, dtype=float).reshape(24)
        psrv_plan = np.asarray(plan.service_commit_kw, dtype=float).reshape(24)

        tariff = np.asarray(plan.tariff_yuan_per_kwh, dtype=float).reshape(24)
        activation = np.asarray(plan.service_activation_factor, dtype=float).reshape(24)
        cap_price = np.asarray(plan.service_capacity_price_yuan_per_kw, dtype=float).reshape(24)
        del_price = np.asarray(plan.service_delivery_price_yuan_per_kwh, dtype=float).reshape(24)
        pen_price = np.asarray(plan.service_penalty_price_yuan_per_kwh, dtype=float).reshape(24)
        expected_penalty_ratio = max(0.0, 1.0 - float(ctx.service_config.delivery_score_floor))
        eta_loss = eta_c - 1.0 / eta_d

        soc = np.zeros(h + 1, dtype=float)
        soc[0] = float(plan.initial_soc)

        pch_exec = np.zeros(h, dtype=float)
        pdis_exec = np.zeros(h, dtype=float)
        psrv_exec = np.zeros(h, dtype=float)

        notes: list[str] = []

        for t in range(h):
            planned_net_power = float(pdis_plan[t] - pch_plan[t])
            planned_service = float(psrv_plan[t])

            if cfg.net_power_execution_mode:
                planned_charge = 0.0 if planned_net_power >= 0 else -planned_net_power
                planned_discharge = planned_net_power if planned_net_power >= 0 else 0.0
            else:
                planned_charge = float(pch_plan[t])
                planned_discharge = float(pdis_plan[t])

            constraint = oracle.get_hour_constraint(
                ctx=ctx,
                day_index=plan.day_index,
                hour_index=t,
                actual_net_load_kw=float(actual_net[t]),
                planned_charge_kw=planned_charge,
                planned_discharge_kw=planned_discharge,
                planned_service_kw=planned_service,
                rated_power_kw=float(plan.rated_power_kw),
                rated_energy_kwh=float(plan.rated_energy_kwh),
                effective_power_cap_kw=eff_power_cap,
                current_soc=float(soc[t]),
                extra={"plan_summary": plan.summary_dict()},
            )

            service_cap = max(0.0, min(planned_service, constraint.service_power_cap_kw, eff_power_cap))
            base_power_cap = max(0.0, eff_power_cap - service_cap)

            max_charge_soc = max(0.0, (plan.soc_max - soc[t]) * rated_energy_kwh / max(eta_c, 1e-9))
            max_discharge_soc = max(0.0, (soc[t] - plan.soc_min) * rated_energy_kwh * eta_d)

            charge_cap = min(base_power_cap, constraint.max_charge_kw, max_charge_soc)
            discharge_cap = min(base_power_cap, constraint.max_discharge_kw, max_discharge_soc)

            executed_base_net = float(np.clip(planned_net_power, -charge_cap, discharge_cap))
            charge = max(0.0, -executed_base_net)
            discharge = max(0.0, executed_base_net)

            if constraint.transformer_limit_kw is not None:
                limit = float(constraint.transformer_limit_kw)
                ge = float(actual_net[t] + charge - discharge)
                if ge > limit:
                    need = ge - limit
                    reduce_charge = min(charge, need)
                    charge -= reduce_charge
                    need -= reduce_charge
                    extra_discharge_room = max(0.0, discharge_cap - discharge)
                    add_discharge = min(extra_discharge_room, need)
                    discharge += add_discharge

            pch_exec[t] = charge
            pdis_exec[t] = discharge
            psrv_exec[t] = service_cap

            soc[t + 1] = (
                soc[t]
                + eta_c * charge / rated_energy_kwh
                - (discharge / eta_d) / rated_energy_kwh
                + eta_loss * activation[t] * service_cap / rated_energy_kwh
            )
            if cfg.enforce_soc_hard_clip:
                soc[t + 1] = float(np.clip(soc[t + 1], plan.soc_min, plan.soc_max))

            if constraint.notes:
                notes.extend(constraint.notes)

        target_terminal_soc = plan.target_terminal_soc
        before_error: float | None = None
        corr_energy = 0.0
        if target_terminal_soc is not None:
            before_error = float(soc[-1] - float(target_terminal_soc))
            tol = cfg.terminal_soc_correction_tolerance_override
            if tol is None:
                tol = float(ctx.operation_config.daily_terminal_soc_tolerance)

            correction_enabled = bool(cfg.enable_terminal_soc_correction) and bool(
                getattr(ctx.operation_config, "enable_terminal_soc_correction", True)
            )
            if correction_enabled and abs(before_error) > tol:
                corr_energy = self._apply_correction(
                    ctx=ctx,
                    plan=plan,
                    actual_net=actual_net,
                    activation=activation,
                    pch_exec=pch_exec,
                    pdis_exec=pdis_exec,
                    psrv_exec=psrv_exec,
                )

        (
            soc,
            grid_exchange,
            slack,
            voltage_penalty,
            arb_rev,
            srv_cap_rev,
            srv_del_rev,
            srv_pen,
            deg_cost,
            tr_pen,
            network_trace,
        ) = self._recompute(
            ctx=ctx,
            plan=plan,
            oracle=oracle,
            actual_net=actual_net,
            tariff=tariff,
            activation=activation,
            cap_price=cap_price,
            del_price=del_price,
            pen_price=pen_price,
            expected_penalty_ratio=expected_penalty_ratio,
            pch_exec=pch_exec,
            pdis_exec=pdis_exec,
            psrv_exec=psrv_exec,
        )

        after_error: float | None = None
        if target_terminal_soc is not None:
            after_error = float(soc[-1] - float(target_terminal_soc))
        soc_expected = (
            soc[:-1]
            + eta_c * pch_exec / rated_energy_kwh
            - (pdis_exec / eta_d) / rated_energy_kwh
            + eta_loss * activation * psrv_exec / rated_energy_kwh
        )
        soc_balance_max_abs = float(np.max(np.abs(soc[1:] - soc_expected))) if soc_expected.size else 0.0

        return RollingDispatchResult(
            day_index=plan.day_index,
            internal_model_id=plan.internal_model_id,
            strategy_id=plan.strategy_id,
            initial_soc=float(plan.initial_soc),
            final_soc=float(soc[-1]),
            hour_count=h,
            actual_load_kw=actual_load,
            actual_pv_kw=actual_pv,
            actual_net_load_kw=actual_net,
            tariff_yuan_per_kwh=tariff,
            planned_charge_kw=pch_plan,
            planned_discharge_kw=pdis_plan,
            planned_service_kw=psrv_plan,
            executed_charge_kw=pch_exec,
            executed_discharge_kw=pdis_exec,
            executed_service_kw=psrv_exec,
            grid_exchange_kw=grid_exchange,
            transformer_slack_kw=slack,
            voltage_penalty_yuan_by_hour=voltage_penalty,
            soc_path=soc,
            arbitrage_revenue_yuan_by_hour=arb_rev,
            service_capacity_revenue_yuan_by_hour=srv_cap_rev,
            service_delivery_revenue_yuan_by_hour=srv_del_rev,
            service_penalty_yuan_by_hour=srv_pen,
            degradation_cost_yuan_by_hour=deg_cost,
            transformer_penalty_yuan_by_hour=tr_pen,
            notes=list(dict.fromkeys(notes)),
            metadata={
                "target_terminal_soc": float(target_terminal_soc) if target_terminal_soc is not None else None,
                "terminal_soc_error_before_correction": before_error,
                "terminal_soc_error_after_correction": after_error,
                "terminal_correction_energy_kwh": float(corr_energy),
                "eta_charge": float(ctx.strategy.eta_charge),
                "eta_discharge": float(ctx.strategy.eta_discharge),
                "service_soc_coeff": float(ctx.strategy.eta_charge - 1.0 / ctx.strategy.eta_discharge),
                "soc_energy_balance_max_abs": soc_balance_max_abs,
            },
            network_trace=network_trace,
        )

    def _apply_correction(self, ctx, plan, actual_net, activation, pch_exec, pdis_exec, psrv_exec) -> float:
        eta_c = float(ctx.strategy.eta_charge)
        eta_d = float(ctx.strategy.eta_discharge)
        rated_energy_kwh = float(plan.rated_energy_kwh)
        eff_power_cap = float(plan.effective_power_cap_kw)
        target_soc = float(plan.target_terminal_soc)

        start = 24 - min(max(1, self.config.terminal_soc_correction_hours), 24)
        corr = 0.0
        for t in range(start, 24):
            soc = self._soc_path(ctx, plan, activation, pch_exec, pdis_exec, psrv_exec)
            remaining = (target_soc - float(soc[-1])) * rated_energy_kwh
            if abs(remaining) <= float(ctx.operation_config.daily_terminal_soc_tolerance) * rated_energy_kwh:
                break

            hours_left = max(1, 24 - t)
            desired = remaining / hours_left
            base_cap = max(
                0.0,
                eff_power_cap * float(self.config.terminal_soc_correction_max_fraction_of_power) - float(psrv_exec[t]),
            )

            ge = float(actual_net[t] + pch_exec[t] - pdis_exec[t])
            transformer_limit = getattr(ctx, "transformer_active_power_limit_kw", None)

            if desired > 0:
                if pdis_exec[t] > 0:
                    removable = min(pdis_exec[t], desired * eta_d)
                    pdis_exec[t] -= removable
                    desired -= removable / max(eta_d, 1e-9)
                    corr += removable / max(eta_d, 1e-9)

                if desired > 1e-9:
                    add_limit = max(0.0, base_cap - pch_exec[t])
                    if transformer_limit is not None:
                        add_limit = min(add_limit, max(0.0, float(transformer_limit) - ge))
                    add = min(add_limit, desired / max(eta_c, 1e-9))
                    pch_exec[t] += add
                    corr += eta_c * add
            else:
                desired = -desired
                if pch_exec[t] > 0:
                    removable = min(pch_exec[t], desired / max(eta_c, 1e-9))
                    pch_exec[t] -= removable
                    desired -= eta_c * removable
                    corr += eta_c * removable

                if desired > 1e-9:
                    add_limit = max(0.0, base_cap - pdis_exec[t])
                    add = min(add_limit, desired * eta_d)
                    pdis_exec[t] += add
                    corr += add / max(eta_d, 1e-9)

        return float(corr)

    def _soc_path(self, ctx, plan, activation, pch_exec, pdis_exec, psrv_exec):
        eta_c = float(ctx.strategy.eta_charge)
        eta_d = float(ctx.strategy.eta_discharge)
        eta_loss = eta_c - 1.0 / eta_d
        rated_energy_kwh = float(plan.rated_energy_kwh)

        soc = np.zeros(25)
        soc[0] = float(plan.initial_soc)
        for t in range(24):
            soc[t + 1] = (
                soc[t]
                + eta_c * pch_exec[t] / rated_energy_kwh
                - (pdis_exec[t] / eta_d) / rated_energy_kwh
                + eta_loss * activation[t] * psrv_exec[t] / rated_energy_kwh
            )
            if self.config.enforce_soc_hard_clip:
                soc[t + 1] = float(np.clip(soc[t + 1], plan.soc_min, plan.soc_max))
        return soc

    def _recompute(
        self,
        ctx,
        plan,
        oracle,
        actual_net,
        tariff,
        activation,
        cap_price,
        del_price,
        pen_price,
        expected_penalty_ratio,
        pch_exec,
        pdis_exec,
        psrv_exec,
    ):
        eta_c = float(ctx.strategy.eta_charge)
        eta_d = float(ctx.strategy.eta_discharge)
        eta_loss = eta_c - 1.0 / eta_d
        rated_energy_kwh = float(plan.rated_energy_kwh)

        soc = np.zeros(25)
        soc[0] = float(plan.initial_soc)
        grid_exchange = np.zeros(24)
        slack = np.zeros(24)
        voltage_penalty = np.zeros(24)
        arb_rev = np.zeros(24)
        srv_cap_rev = np.zeros(24)
        srv_del_rev = np.zeros(24)
        srv_pen = np.zeros(24)
        deg_cost = np.zeros(24)
        tr_pen = np.zeros(24)
        network_trace: list[dict[str, Any]] = []

        for t in range(24):
            ge = float(actual_net[t] + pch_exec[t] - pdis_exec[t])
            constraint = oracle.get_hour_constraint(
                ctx=ctx,
                day_index=plan.day_index,
                hour_index=t,
                actual_net_load_kw=float(actual_net[t]),
                planned_charge_kw=float(pch_exec[t]),
                planned_discharge_kw=float(pdis_exec[t]),
                planned_service_kw=float(psrv_exec[t]),
                rated_power_kw=float(plan.rated_power_kw),
                rated_energy_kwh=float(plan.rated_energy_kwh),
                effective_power_cap_kw=float(plan.effective_power_cap_kw),
                current_soc=float(soc[t]),
                extra={"plan_summary": plan.summary_dict(), "capture_network_trace": True},
            )
            meta = constraint.metadata or {}
            has_loss_trace = any(
                meta.get(key) is not None
                for key in (
                    "opendss_loss_baseline_kw",
                    "opendss_loss_with_storage_kw",
                    "opendss_loss_reduction_kwh",
                )
            )
            has_scalar_network_trace = any(
                meta.get(key) is not None
                for key in (
                    "baseline_voltage_min_pu",
                    "baseline_voltage_max_pu",
                    "voltage_min_pu",
                    "voltage_max_pu",
                    "voltage_violation_pu",
                    "storage_voltage_violation_increment_pu",
                    "target_voltage_min_pu",
                    "target_voltage_max_pu",
                    "target_voltage_violation_pu",
                    "storage_target_voltage_violation_increment_pu",
                    "line_current_max_a",
                    "line_loading_max_pct",
                    "target_line_current_max_a",
                    "target_line_loading_max_pct",
                    "target_line_overload_pct",
                    "opendss_solve_converged",
                )
            )
            if meta.get("bus_voltages") or meta.get("line_currents") or has_loss_trace or has_scalar_network_trace:
                network_trace.append(
                    {
                        "day_index": int(plan.day_index) + 1,
                        "day_index_zero_based": int(plan.day_index),
                        "hour": int(t),
                        "opendss_used": bool(meta.get("opendss_used", False)),
                        "opendss_baseline_converged": meta.get("opendss_baseline_converged"),
                        "opendss_storage_converged": meta.get("opendss_storage_converged"),
                        "opendss_solve_converged": meta.get("opendss_solve_converged"),
                        "target_bus": meta.get("target_bus"),
                        "target_load": meta.get("target_load"),
                        "baseline_voltage_pu_min": meta.get("baseline_voltage_min_pu"),
                        "baseline_voltage_pu_max": meta.get("baseline_voltage_max_pu"),
                        "baseline_voltage_violation_pu": meta.get("baseline_voltage_violation_pu"),
                        "baseline_line_current_max_a": meta.get("baseline_line_current_max_a"),
                        "baseline_line_loading_max_pct": meta.get("baseline_line_loading_max_pct"),
                        "baseline_target_voltage_pu_min": meta.get("baseline_target_voltage_min_pu"),
                        "baseline_target_voltage_pu_max": meta.get("baseline_target_voltage_max_pu"),
                        "baseline_target_voltage_violation_pu": meta.get("baseline_target_voltage_violation_pu"),
                        "baseline_target_line_current_max_a": meta.get("baseline_target_line_current_max_a"),
                        "baseline_target_line_loading_max_pct": meta.get("baseline_target_line_loading_max_pct"),
                        "baseline_target_line_overload_pct": meta.get("baseline_target_line_overload_pct"),
                        "voltage_pu_min": meta.get("voltage_min_pu"),
                        "voltage_pu_max": meta.get("voltage_max_pu"),
                        "voltage_violation_pu": meta.get("voltage_violation_pu"),
                        "storage_voltage_violation_increment_pu": meta.get("storage_voltage_violation_increment_pu"),
                        "target_voltage_pu_min": meta.get("target_voltage_min_pu"),
                        "target_voltage_pu_max": meta.get("target_voltage_max_pu"),
                        "target_voltage_violation_pu": meta.get("target_voltage_violation_pu"),
                        "storage_target_voltage_violation_increment_pu": meta.get("storage_target_voltage_violation_increment_pu"),
                        "line_current_max_a": meta.get("line_current_max_a"),
                        "line_loading_max_pct": meta.get("line_loading_max_pct"),
                        "target_line_current_max_a": meta.get("target_line_current_max_a"),
                        "target_line_loading_max_pct": meta.get("target_line_loading_max_pct"),
                        "target_line_overload_pct": meta.get("target_line_overload_pct"),
                        "storage_target_line_overload_increment_pct": meta.get("storage_target_line_overload_increment_pct"),
                        "opendss_loss_baseline_kw": meta.get("opendss_loss_baseline_kw"),
                        "opendss_loss_baseline_kvar": meta.get("opendss_loss_baseline_kvar"),
                        "opendss_loss_with_storage_kw": meta.get("opendss_loss_with_storage_kw"),
                        "opendss_loss_with_storage_kvar": meta.get("opendss_loss_with_storage_kvar"),
                        "opendss_loss_reduction_kw": meta.get("opendss_loss_reduction_kw"),
                        "opendss_loss_reduction_kwh": meta.get("opendss_loss_reduction_kwh"),
                        "opendss_loss_reduction_positive_kwh": meta.get("opendss_loss_reduction_positive_kwh"),
                        "opendss_loss_source": meta.get("opendss_loss_source"),
                        "baseline_bus_voltages": meta.get("baseline_bus_voltages") or [],
                        "baseline_line_currents": meta.get("baseline_line_currents") or [],
                        "baseline_target_line_currents": meta.get("baseline_target_line_currents") or [],
                        "bus_voltages": meta.get("bus_voltages") or [],
                        "line_currents": meta.get("line_currents") or [],
                        "target_line_currents": meta.get("target_line_currents") or [],
                    }
                )
            if constraint.transformer_limit_kw is not None:
                slack[t] = max(0.0, ge - float(constraint.transformer_limit_kw))

            grid_exchange[t] = ge
            soc[t + 1] = (
                soc[t]
                + eta_c * pch_exec[t] / rated_energy_kwh
                - (pdis_exec[t] / eta_d) / rated_energy_kwh
                + eta_loss * activation[t] * psrv_exec[t] / rated_energy_kwh
            )
            if self.config.enforce_soc_hard_clip:
                soc[t + 1] = float(np.clip(soc[t + 1], plan.soc_min, plan.soc_max))

            voltage_penalty[t] = float(constraint.voltage_penalty_yuan)
            arb_rev[t] = float(tariff[t] * (pdis_exec[t] - pch_exec[t]))
            srv_cap_rev[t] = float(cap_price[t] * psrv_exec[t])
            srv_del_rev[t] = float(del_price[t] * activation[t] * psrv_exec[t])

            service_shortfall = max(0.0, float(plan.service_commit_kw[t]) - psrv_exec[t])
            srv_pen[t] = float(pen_price[t] * activation[t] * expected_penalty_ratio * service_shortfall)

            deg_coeff = float(ctx.strategy.degradation_cost_yuan_per_kwh_throughput)
            deg_cost[t] = float(
                deg_coeff
                * (
                    pch_exec[t]
                    + pdis_exec[t]
                    + self.config.degradation_weight_service * activation[t] * psrv_exec[t]
                )
            )
            tr_pen[t] = float(self.config.transformer_violation_penalty_yuan_per_kwh * slack[t])

        return soc, grid_exchange, slack, voltage_penalty, arb_rev, srv_cap_rev, srv_del_rev, srv_pen, deg_cost, tr_pen, network_trace
