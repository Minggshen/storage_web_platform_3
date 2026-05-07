from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable
import warnings

import cvxpy as cp
import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.simulation.dispatch_result_models import DayAheadDispatchPlan, DayAheadObjectiveBreakdown
from storage_engine_project.simulation.service_headroom import (
    DailyServiceProfile,
    build_daily_service_profile,
    service_soc_reserve_ratio_expr,
)


@dataclass(slots=True)
class DayAheadSchedulerConfig:
    preferred_solvers: tuple[str, ...] = ("ECOS", "SCS")
    terminal_soc_penalty_yuan_per_unit_sq: float = 30000.0
    transformer_violation_penalty_yuan_per_kwh: float = 300.0
    throughput_penalty_yuan_per_kwh: float = 0.001
    smoothness_penalty_yuan_per_kw_change_sq: float = 0.0005
    service_degradation_weight: float = 1.0
    allow_fallback_rule: bool = True
    validate_candidate_before_solve: bool = True

    enable_plan_cache: bool = True

    log_input_signature: bool = False
    log_cache_hit: bool = False
    log_solver_success: bool = False
    log_solver_failure: bool = True
    log_solver_inaccurate: bool = True
    print_solver_order: bool = False

    prefer_solver_order_when_status_ties: bool = True


class DayAheadScheduler:
    def __init__(self, config: DayAheadSchedulerConfig | None = None) -> None:
        self.config = config or DayAheadSchedulerConfig()
        self._solver_name_cache = tuple(self._iter_available_solvers(self.config.preferred_solvers))
        self._solver_priority = {name: idx for idx, name in enumerate(self._solver_name_cache)}
        self._plan_cache: dict[tuple[Any, ...], DayAheadDispatchPlan] = {}
        if self.config.print_solver_order:
            print(f"[日前调度器] 当前求解器顺序：{self._solver_name_cache}")

    def schedule_day(
        self,
        ctx: AnnualOperationContext,
        day_index: int,
        rated_power_kw: float,
        rated_energy_kwh: float,
        initial_soc: float,
        target_terminal_soc: float | None = None,
    ) -> DayAheadDispatchPlan:
        if not (0 <= day_index < 365):
            raise IndexError(f"day_index 必须在 [0, 364] 内，当前为 {day_index}")

        strategy = ctx.strategy
        safe_cfg = ctx.safety_config
        op_cfg = ctx.operation_config

        if self.config.validate_candidate_before_solve:
            errors = strategy.validate_candidate(rated_power_kw, rated_energy_kwh)
            if errors:
                raise ValueError(
                    f"候选方案不满足设备策略约束：strategy_id={strategy.strategy_id}；问题：{'；'.join(errors)}"
                )

        derate = safe_cfg.resolve_power_derate(strategy.safety_level)
        effective_power_cap_kw = float(rated_power_kw) * float(derate)
        soc_min, soc_max = safe_cfg.resolve_soc_bounds(strategy)
        terminal_soc_target = self._resolve_terminal_soc_target(
            ctx=ctx,
            initial_soc=initial_soc,
            target_terminal_soc=target_terminal_soc,
            soc_min=soc_min,
            soc_max=soc_max,
        )

        load_kw = np.asarray(ctx.load_matrix_kw[day_index], dtype=float).reshape(24)
        pv_kw = np.asarray(ctx.pv_matrix_kw[day_index], dtype=float).reshape(24)
        net_load_kw = np.asarray(ctx.net_load_matrix_kw[day_index], dtype=float).reshape(24)
        tariff = np.asarray(ctx.tariff_matrix_yuan_per_kwh[day_index], dtype=float).reshape(24)

        if self.config.log_input_signature:
            print(
                f"[日前调度输入] day={day_index + 1}, load_sum={float(np.sum(load_kw)):.4f}, "
                f"pv_sum={float(np.sum(pv_kw)):.4f}, tariff_sum={float(np.sum(tariff)):.4f}, "
                f"load_min={float(np.min(load_kw)):.4f}, load_max={float(np.max(load_kw)):.4f}"
            )

        svc_profile = build_daily_service_profile(
            ctx=ctx,
            day_index=day_index,
            effective_power_cap_kw=effective_power_cap_kw,
        )

        cache_key = self._build_cache_key(
            ctx=ctx,
            rated_power_kw=float(rated_power_kw),
            rated_energy_kwh=float(rated_energy_kwh),
            initial_soc=float(np.clip(initial_soc, soc_min, soc_max)),
            terminal_soc_target=terminal_soc_target,
            load_kw=load_kw,
            pv_kw=pv_kw,
            tariff=tariff,
            svc_profile=svc_profile,
        )
        if self.config.enable_plan_cache and cache_key in self._plan_cache:
            cached = self._plan_cache[cache_key]
            if self.config.log_cache_hit:
                print(f"[日前调度缓存命中] day={day_index + 1}, strategy={strategy.strategy_id}")
            return replace(cached, day_index=day_index)

        try:
            plan = self._solve_convex_day(
                ctx=ctx,
                day_index=day_index,
                rated_power_kw=float(rated_power_kw),
                rated_energy_kwh=float(rated_energy_kwh),
                effective_power_cap_kw=effective_power_cap_kw,
                soc_min=soc_min,
                soc_max=soc_max,
                initial_soc=float(np.clip(initial_soc, soc_min, soc_max)),
                terminal_soc_target=terminal_soc_target,
                load_kw=load_kw,
                pv_kw=pv_kw,
                net_load_kw=net_load_kw,
                tariff=tariff,
                svc_profile=svc_profile,
            )
        except Exception as exc:
            if not self.config.allow_fallback_rule:
                raise
            plan = self._fallback_rule_schedule(
                ctx=ctx,
                day_index=day_index,
                rated_power_kw=float(rated_power_kw),
                rated_energy_kwh=float(rated_energy_kwh),
                effective_power_cap_kw=effective_power_cap_kw,
                soc_min=soc_min,
                soc_max=soc_max,
                initial_soc=float(np.clip(initial_soc, soc_min, soc_max)),
                terminal_soc_target=terminal_soc_target,
                load_kw=load_kw,
                pv_kw=pv_kw,
                net_load_kw=net_load_kw,
                tariff=tariff,
                svc_profile=svc_profile,
                reason=str(exc),
            )

        if self.config.enable_plan_cache:
            self._plan_cache[cache_key] = plan
        return plan

    def _build_cache_key(
        self,
        ctx: AnnualOperationContext,
        rated_power_kw: float,
        rated_energy_kwh: float,
        initial_soc: float,
        terminal_soc_target: float | None,
        load_kw: np.ndarray,
        pv_kw: np.ndarray,
        tariff: np.ndarray,
        svc_profile: DailyServiceProfile,
    ) -> tuple[Any, ...]:
        return (
            ctx.strategy.strategy_id,
            round(rated_power_kw, 4),
            round(rated_energy_kwh, 4),
            round(initial_soc, 4),
            None if terminal_soc_target is None else round(terminal_soc_target, 4),
            tuple(np.round(load_kw, 3)),
            tuple(np.round(pv_kw, 3)),
            tuple(np.round(tariff, 4)),
            tuple(np.round(svc_profile.availability, 3)),
            tuple(np.round(svc_profile.activation_factor, 3)),
        )

    def _solve_convex_day(
        self,
        ctx: AnnualOperationContext,
        day_index: int,
        rated_power_kw: float,
        rated_energy_kwh: float,
        effective_power_cap_kw: float,
        soc_min: float,
        soc_max: float,
        initial_soc: float,
        terminal_soc_target: float | None,
        load_kw: np.ndarray,
        pv_kw: np.ndarray,
        net_load_kw: np.ndarray,
        tariff: np.ndarray,
        svc_profile: DailyServiceProfile,
    ) -> DayAheadDispatchPlan:
        h = 24
        cfg = self.config
        op_cfg = ctx.operation_config
        strategy = ctx.strategy
        eta_c = float(strategy.eta_charge)
        eta_d = float(strategy.eta_discharge)
        energy_kwh = float(rated_energy_kwh)
        eta_loss = eta_c - 1.0 / eta_d
        deg_coeff = float(strategy.degradation_cost_yuan_per_kwh_throughput)
        transformer_limit_kw = ctx.transformer_active_power_limit_kw
        enable_transformer_limit = op_cfg.enable_transformer_limit and transformer_limit_kw is not None

        p_charge = cp.Variable(h, nonneg=True)
        p_discharge = cp.Variable(h, nonneg=True)
        p_service = cp.Variable(h, nonneg=True)
        soc = cp.Variable(h + 1)
        transformer_slack = cp.Variable(h, nonneg=True)
        constraints: list = [soc[0] == initial_soc]

        for t in range(h):
            service_soc_loss = eta_loss * float(svc_profile.activation_factor[t]) * p_service[t] / energy_kwh
            soc_next = soc[t] + eta_c * p_charge[t] / energy_kwh - (p_discharge[t] / eta_d) / energy_kwh + service_soc_loss
            constraints.append(soc[t + 1] == soc_next)
            constraints.append(p_charge[t] + p_service[t] <= effective_power_cap_kw)
            constraints.append(p_discharge[t] + p_service[t] <= effective_power_cap_kw)
            constraints.append(p_service[t] <= float(svc_profile.availability[t]) * float(svc_profile.max_service_power_kw))
            if not strategy.allow_grid_charging:
                pv_surplus_kw = max(0.0, float(pv_kw[t] - load_kw[t]))
                constraints.append(p_charge[t] <= pv_surplus_kw)
            reserve_soc_ratio = service_soc_reserve_ratio_expr(
                p_service[t],
                effective_power_cap_kw=effective_power_cap_kw,
                headroom_ratio=svc_profile.headroom_ratio,
            )
            constraints.append(soc[t] >= soc_min + reserve_soc_ratio)
            constraints.append(soc[t] <= soc_max - reserve_soc_ratio)
            constraints.append(soc[t + 1] >= soc_min + reserve_soc_ratio)
            constraints.append(soc[t + 1] <= soc_max - reserve_soc_ratio)
            if enable_transformer_limit:
                grid_exchange_expr = net_load_kw[t] + p_charge[t] - p_discharge[t]
                constraints.append(grid_exchange_expr <= float(transformer_limit_kw) + transformer_slack[t])
            else:
                constraints.append(transformer_slack[t] == 0.0)

        terminal_penalty_expr = 0.0
        if terminal_soc_target is not None and op_cfg.enforce_daily_terminal_soc:
            tol = float(op_cfg.daily_terminal_soc_tolerance)
            constraints.append(soc[-1] >= terminal_soc_target - tol)
            constraints.append(soc[-1] <= terminal_soc_target + tol)
        elif terminal_soc_target is not None:
            terminal_penalty_expr = float(cfg.terminal_soc_penalty_yuan_per_unit_sq) * cp.square(soc[-1] - terminal_soc_target)

        arbitrage_revenue = cp.sum(cp.multiply(tariff, p_discharge - p_charge))
        service_capacity_revenue = cp.sum(cp.multiply(svc_profile.capacity_price_yuan_per_kw, p_service))
        service_delivery_revenue = cp.sum(cp.multiply(svc_profile.delivery_price_yuan_per_kwh * svc_profile.activation_factor, p_service))
        service_expected_penalty = cp.sum(cp.multiply(svc_profile.penalty_price_yuan_per_kwh * svc_profile.activation_factor * float(svc_profile.expected_penalty_ratio), p_service))
        degradation_cost = deg_coeff * cp.sum(p_charge + p_discharge + float(cfg.service_degradation_weight) * cp.multiply(svc_profile.activation_factor, p_service))
        throughput_penalty = float(cfg.throughput_penalty_yuan_per_kwh) * cp.sum(p_charge + p_discharge + p_service)
        net_battery_power = p_discharge - p_charge
        smoothness_penalty = 0.0
        if h >= 2 and cfg.smoothness_penalty_yuan_per_kw_change_sq > 0:
            smoothness_penalty = float(cfg.smoothness_penalty_yuan_per_kw_change_sq) * cp.sum_squares(net_battery_power[1:] - net_battery_power[:-1])
        transformer_penalty = 0.0
        if enable_transformer_limit:
            transformer_penalty = float(cfg.transformer_violation_penalty_yuan_per_kwh) * cp.sum(transformer_slack)

        objective_value = (
            arbitrage_revenue
            + service_capacity_revenue
            + service_delivery_revenue
            - service_expected_penalty
            - degradation_cost
            - throughput_penalty
            - smoothness_penalty
            - transformer_penalty
            - terminal_penalty_expr
        )
        problem = cp.Problem(cp.Maximize(objective_value), constraints)

        candidates: list[dict[str, Any]] = []
        last_error = None
        for solver_name in self._solver_name_cache:
            if not hasattr(cp, solver_name):
                continue
            solver = getattr(cp, solver_name)
            solve_kwargs = {"warm_start": True, "verbose": False}
            if solver_name == "ECOS":
                solve_kwargs.update({"max_iters": 8000, "abstol": 1e-7, "reltol": 1e-7, "feastol": 1e-7})
            elif solver_name == "SCS":
                solve_kwargs.update({"max_iters": 50000, "eps": 5e-6, "acceleration_lookback": 20})

            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Solution may be inaccurate.*")
                    problem.solve(solver=solver, **solve_kwargs)
                solver_status = str(problem.status).lower()

                should_print = (
                    self.config.log_solver_success
                    or (
                        self.config.log_solver_inaccurate
                        and problem.status == cp.OPTIMAL_INACCURATE
                    )
                )
                if should_print:
                    print(
                        f"[日前调度求解] day={day_index + 1}, solver={solver_name}, "
                        f"status={solver_status}, objective={problem.value}"
                    )

                if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
                    continue
                pch = np.maximum(np.asarray(p_charge.value, dtype=float).reshape(h), 0.0)
                pdis = np.maximum(np.asarray(p_discharge.value, dtype=float).reshape(h), 0.0)
                psrv = np.maximum(np.asarray(p_service.value, dtype=float).reshape(h), 0.0)
                soc_path = np.asarray(soc.value, dtype=float).reshape(h + 1)
                slack = np.maximum(np.asarray(transformer_slack.value, dtype=float).reshape(h), 0.0)
                if np.any(~np.isfinite(soc_path)):
                    continue

                terminal_soc_error = float(abs(soc_path[-1] - terminal_soc_target)) if terminal_soc_target is not None else 0.0
                slack_sum = float(np.sum(slack))
                simultaneous_sum = float(np.sum(np.minimum(pch, pdis)))

                candidates.append(
                    {
                        "solver_name": solver_name,
                        "solver_status": str(problem.status),
                        "objective": float(problem.value) if problem.value is not None else -1e18,
                        "pch": pch,
                        "pdis": pdis,
                        "psrv": psrv,
                        "soc_path": soc_path,
                        "slack": slack,
                        "terminal_soc_error": terminal_soc_error,
                        "slack_sum": slack_sum,
                        "simultaneous_sum": simultaneous_sum,
                    }
                )
            except Exception as exc:
                last_error = exc
                if self.config.log_solver_failure:
                    print(f"[日前调度求解] day={day_index + 1}, solver={solver_name} 求解失败：{exc}")
                continue

        if not candidates:
            raise RuntimeError(f"日前调度求解失败，last_error={last_error}")

        def _status_rank(status: str) -> int:
            s = status.upper()
            if s == "OPTIMAL":
                return 2
            if s == "OPTIMAL_INACCURATE":
                return 1
            return 0

        def _solver_rank(name: str) -> int:
            return -self._solver_priority.get(name, 999)

        ranked = sorted(
            candidates,
            key=lambda item: (
                _status_rank(item["solver_status"]),
                -item["slack_sum"],
                -item["terminal_soc_error"],
                item["objective"],
                -item["simultaneous_sum"],
                _solver_rank(item["solver_name"]) if self.config.prefer_solver_order_when_status_ties else 0,
            ),
            reverse=True,
        )
        chosen = ranked[0]
        if chosen["solver_status"].upper() == "OPTIMAL_INACCURATE" and self.config.log_solver_inaccurate:
            print(
                f"[日前调度求解] day={day_index + 1}, 采用近似最优解，"
                f"solver={chosen['solver_name']}, objective={chosen['objective']}"
            )

        pch = chosen["pch"]
        pdis = chosen["pdis"]
        psrv = chosen["psrv"]
        soc_path = chosen["soc_path"]
        slack = chosen["slack"]
        grid_exchange = net_load_kw + pch - pdis

        breakdown = DayAheadObjectiveBreakdown(
            arbitrage_revenue_yuan=float(np.sum(tariff * (pdis - pch))),
            service_capacity_revenue_yuan=float(np.sum(svc_profile.capacity_price_yuan_per_kw * psrv)),
            service_delivery_revenue_yuan=float(np.sum(svc_profile.delivery_price_yuan_per_kwh * svc_profile.activation_factor * psrv)),
            service_expected_penalty_yuan=float(np.sum(svc_profile.penalty_price_yuan_per_kwh * svc_profile.activation_factor * svc_profile.expected_penalty_ratio * psrv)),
            degradation_cost_yuan=float(deg_coeff * np.sum(pch + pdis + float(cfg.service_degradation_weight) * svc_profile.activation_factor * psrv)),
            transformer_penalty_yuan=float(float(cfg.transformer_violation_penalty_yuan_per_kwh) * np.sum(slack)),
            throughput_penalty_yuan=float(float(cfg.throughput_penalty_yuan_per_kwh) * np.sum(pch + pdis + psrv)),
            smoothness_penalty_yuan=float(float(cfg.smoothness_penalty_yuan_per_kw_change_sq) * np.sum(((pdis - pch)[1:] - (pdis - pch)[:-1]) ** 2)) if h >= 2 else 0.0,
            terminal_soc_penalty_yuan=0.0 if (op_cfg.enforce_daily_terminal_soc or terminal_soc_target is None) else float(float(cfg.terminal_soc_penalty_yuan_per_unit_sq) * (soc_path[-1] - terminal_soc_target) ** 2),
            total_objective_value_yuan=float(chosen["objective"]),
        )
        notes = []
        if enable_transformer_limit:
            notes.append("已启用变压器有功容量软约束。")
        if not strategy.allow_grid_charging:
            notes.append("当前策略禁止电网充电，已按 PV 剩余电量近似约束。")
        terminal_soc_error = float(abs(float(soc_path[-1]) - float(terminal_soc_target))) if terminal_soc_target is not None else None
        return DayAheadDispatchPlan(
            day_index=day_index,
            internal_model_id=ctx.internal_model_id,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.strategy_name,
            rated_power_kw=rated_power_kw,
            rated_energy_kwh=rated_energy_kwh,
            effective_power_cap_kw=effective_power_cap_kw,
            soc_min=soc_min,
            soc_max=soc_max,
            initial_soc=initial_soc,
            target_terminal_soc=terminal_soc_target,
            final_soc=float(soc_path[-1]),
            hour_count=h,
            load_kw=load_kw,
            pv_kw=pv_kw,
            net_load_kw=net_load_kw,
            tariff_yuan_per_kwh=tariff,
            service_availability=svc_profile.availability,
            service_activation_factor=svc_profile.activation_factor,
            service_capacity_price_yuan_per_kw=svc_profile.capacity_price_yuan_per_kw,
            service_delivery_price_yuan_per_kwh=svc_profile.delivery_price_yuan_per_kwh,
            service_penalty_price_yuan_per_kwh=svc_profile.penalty_price_yuan_per_kwh,
            charge_kw=pch,
            discharge_kw=pdis,
            service_commit_kw=psrv,
            soc_path=soc_path,
            grid_exchange_kw=grid_exchange,
            transformer_slack_kw=slack,
            objective_breakdown=breakdown,
            solver_status=str(chosen["solver_status"]),
            used_fallback=False,
            notes=notes,
            metadata={
                "transformer_limit_kw": transformer_limit_kw,
                "service_enabled": svc_profile.enabled,
                "service_max_power_kw": svc_profile.max_service_power_kw,
                "service_headroom_ratio": svc_profile.headroom_ratio,
                "solver_name": chosen["solver_name"],
                "solver_candidates": [
                    (
                        c["solver_name"],
                        c["solver_status"],
                        c["objective"],
                        c["terminal_soc_error"],
                        c["slack_sum"],
                    )
                    for c in ranked
                ],
                "planned_terminal_soc_error": terminal_soc_error,
            },
        )

    def _fallback_rule_schedule(
        self,
        ctx: AnnualOperationContext,
        day_index: int,
        rated_power_kw: float,
        rated_energy_kwh: float,
        effective_power_cap_kw: float,
        soc_min: float,
        soc_max: float,
        initial_soc: float,
        terminal_soc_target: float | None,
        load_kw: np.ndarray,
        pv_kw: np.ndarray,
        net_load_kw: np.ndarray,
        tariff: np.ndarray,
        svc_profile: DailyServiceProfile,
        reason: str,
    ) -> DayAheadDispatchPlan:
        h = 24
        strategy = ctx.strategy
        notes = [f"优化器求解失败，已使用规则回退：{reason}"]
        charge = np.zeros(h, dtype=float)
        discharge = np.zeros(h, dtype=float)
        service = np.zeros(h, dtype=float)
        soc = np.zeros(h + 1, dtype=float)
        soc[0] = initial_soc
        eta_c = float(strategy.eta_charge)
        eta_d = float(strategy.eta_discharge)
        eta_loss = eta_c - 1.0 / eta_d
        low_th = float(np.quantile(tariff, 0.25))
        high_th = float(np.quantile(tariff, 0.75))
        for t in range(h):
            local_soc_min = soc_min
            local_soc_max = soc_max
            available_charge_power = max(0.0, effective_power_cap_kw)
            available_discharge_power = max(0.0, effective_power_cap_kw)
            if tariff[t] <= low_th and soc[t] < local_soc_max - 1e-6:
                max_charge_by_soc = (local_soc_max - soc[t]) * rated_energy_kwh / max(eta_c, 1e-9)
                charge[t] = min(available_charge_power, max_charge_by_soc)
            elif tariff[t] >= high_th and soc[t] > local_soc_min + 1e-6:
                max_discharge_by_soc = (soc[t] - local_soc_min) * rated_energy_kwh * eta_d
                discharge[t] = min(available_discharge_power, max_discharge_by_soc)
            soc[t + 1] = soc[t] + eta_c * charge[t] / rated_energy_kwh - (discharge[t] / eta_d) / rated_energy_kwh + eta_loss * svc_profile.activation_factor[t] * service[t] / rated_energy_kwh
            soc[t + 1] = float(np.clip(soc[t + 1], local_soc_min, local_soc_max))
        grid_exchange = net_load_kw + charge - discharge
        transformer_limit_kw = ctx.transformer_active_power_limit_kw
        slack = np.maximum(grid_exchange - float(transformer_limit_kw), 0.0) if ctx.operation_config.enable_transformer_limit and transformer_limit_kw is not None else np.zeros(h, dtype=float)
        deg_coeff = float(strategy.degradation_cost_yuan_per_kwh_throughput)
        smoothness_penalty = 0.0
        if h >= 2:
            delta = (discharge - charge)[1:] - (discharge - charge)[:-1]
            smoothness_penalty = float(self.config.smoothness_penalty_yuan_per_kw_change_sq * np.sum(delta ** 2))
        breakdown = DayAheadObjectiveBreakdown(
            arbitrage_revenue_yuan=float(np.sum(tariff * (discharge - charge))),
            service_capacity_revenue_yuan=0.0,
            service_delivery_revenue_yuan=0.0,
            service_expected_penalty_yuan=0.0,
            degradation_cost_yuan=float(deg_coeff * np.sum(charge + discharge)),
            transformer_penalty_yuan=float(self.config.transformer_violation_penalty_yuan_per_kwh * np.sum(slack)),
            throughput_penalty_yuan=float(self.config.throughput_penalty_yuan_per_kwh * np.sum(charge + discharge)),
            smoothness_penalty_yuan=smoothness_penalty,
            terminal_soc_penalty_yuan=0.0 if terminal_soc_target is None else float(self.config.terminal_soc_penalty_yuan_per_unit_sq * (soc[-1] - terminal_soc_target) ** 2),
            total_objective_value_yuan=0.0,
        )
        return DayAheadDispatchPlan(
            day_index=day_index,
            internal_model_id=ctx.internal_model_id,
            strategy_id=strategy.strategy_id,
            strategy_name=strategy.strategy_name,
            rated_power_kw=rated_power_kw,
            rated_energy_kwh=rated_energy_kwh,
            effective_power_cap_kw=effective_power_cap_kw,
            soc_min=soc_min,
            soc_max=soc_max,
            initial_soc=initial_soc,
            target_terminal_soc=terminal_soc_target,
            final_soc=float(soc[-1]),
            hour_count=h,
            load_kw=load_kw,
            pv_kw=pv_kw,
            net_load_kw=net_load_kw,
            tariff_yuan_per_kwh=tariff,
            service_availability=svc_profile.availability,
            service_activation_factor=svc_profile.activation_factor,
            service_capacity_price_yuan_per_kw=svc_profile.capacity_price_yuan_per_kw,
            service_delivery_price_yuan_per_kwh=svc_profile.delivery_price_yuan_per_kwh,
            service_penalty_price_yuan_per_kwh=svc_profile.penalty_price_yuan_per_kwh,
            charge_kw=charge,
            discharge_kw=discharge,
            service_commit_kw=service,
            soc_path=soc,
            grid_exchange_kw=grid_exchange,
            transformer_slack_kw=slack,
            objective_breakdown=breakdown,
            solver_status="fallback_rule",
            used_fallback=True,
            notes=notes,
            metadata={
                "transformer_limit_kw": transformer_limit_kw,
                "service_enabled": svc_profile.enabled,
                "service_max_power_kw": svc_profile.max_service_power_kw,
                "service_headroom_ratio": svc_profile.headroom_ratio,
                "planned_terminal_soc_error": None if terminal_soc_target is None else float(abs(float(soc[-1]) - float(terminal_soc_target))),
            },
        )

    def _resolve_terminal_soc_target(
        self,
        ctx: AnnualOperationContext,
        initial_soc: float,
        target_terminal_soc: float | None,
        soc_min: float,
        soc_max: float,
    ) -> float | None:
        if target_terminal_soc is not None:
            return float(np.clip(target_terminal_soc, soc_min, soc_max))
        mode = str(ctx.operation_config.terminal_soc_mode).strip().lower()
        if mode in {"free", "none"}:
            return None
        if mode == "fixed":
            return float(np.clip(getattr(ctx.operation_config, "fixed_terminal_soc_target", initial_soc), soc_min, soc_max))
        if mode == "strategy_mid":
            return float(np.clip(0.5 * (soc_min + soc_max), soc_min, soc_max))
        return float(np.clip(initial_soc, soc_min, soc_max))

    @staticmethod
    def _iter_available_solvers(preferred_solvers: Iterable[str]) -> Iterable[str]:
        seen: set[str] = set()
        for name in preferred_solvers:
            name = str(name).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            yield name
