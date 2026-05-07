from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.optimization.optimization_models import ScreeningResult, StorageDecision


@dataclass(slots=True)
class CandidateScreeningConfig:
    min_power_to_peak_load_ratio: float = 0.02
    max_power_to_peak_load_ratio: float = 1.20
    max_power_to_transformer_limit_ratio: float = 1.10
    max_energy_to_daily_mean_load_ratio: float = 8.0
    duration_tolerance_h: float = 0.05
    max_energy_to_annual_mean_load_ratio: float = 12.0
    allowed_strategy_ids: tuple[str, ...] = ()
    blocked_strategy_ids: tuple[str, ...] = ()
    allow_non_service_strategy_when_service_enabled: bool = True


class CandidateScreeningEngine:
    def __init__(self, config: CandidateScreeningConfig | None = None) -> None:
        self.config = config or CandidateScreeningConfig()

    def _resolve_strategy(self, ctx: AnnualOperationContext, strategy_id: str):
        if ctx.strategy.strategy_id == strategy_id:
            return ctx.strategy
        if ctx.strategy_library and strategy_id in ctx.strategy_library:
            return ctx.strategy_library[strategy_id]
        return None

    @staticmethod
    def _strategy_boundary(ctx: AnnualOperationContext, strategy_id: str) -> dict | None:
        raw = ctx.meta.get("configuration_boundaries") if isinstance(ctx.meta, dict) else None
        if not isinstance(raw, dict):
            return None
        item = raw.get(strategy_id)
        return item if isinstance(item, dict) else None

    @staticmethod
    def _float_or_none(value) -> float | None:
        try:
            number = float(value)
        except Exception:
            return None
        return number if np.isfinite(number) else None

    def screen(
        self,
        ctx: AnnualOperationContext,
        decision: StorageDecision,
    ) -> ScreeningResult:
        cfg = self.config
        strategy = self._resolve_strategy(ctx, decision.strategy_id)

        messages: list[str] = []
        metadata: dict[str, float | str | bool] = {}

        if cfg.allowed_strategy_ids and decision.strategy_id not in set(cfg.allowed_strategy_ids):
            return ScreeningResult(
                is_feasible=False,
                messages=[f"策略 {decision.strategy_id} 不在 allowed_strategy_ids 中。"],
            )

        if decision.strategy_id in set(cfg.blocked_strategy_ids):
            return ScreeningResult(
                is_feasible=False,
                messages=[f"策略 {decision.strategy_id} 位于 blocked_strategy_ids 中。"],
            )

        if strategy is None:
            return ScreeningResult(
                is_feasible=False,
                messages=[f"上下文中找不到策略 {decision.strategy_id}。"],
            )

        validate_errors = strategy.validate_candidate(
            power_kw=float(decision.rated_power_kw),
            energy_kwh=float(decision.rated_energy_kwh),
        )
        if validate_errors:
            return ScreeningResult(
                is_feasible=False,
                messages=[f"设备策略校验失败：{'；'.join(validate_errors)}"],
            )

        net_load = np.asarray(ctx.net_load_matrix_kw, dtype=float)
        peak_load_kw = float(np.max(np.maximum(net_load, 0.0)))
        daily_mean_load_kwh = float(np.mean(np.sum(np.maximum(net_load, 0.0), axis=1)))
        annual_mean_load_kw = float(np.mean(np.maximum(net_load, 0.0)))

        metadata["peak_load_kw"] = peak_load_kw
        metadata["daily_mean_load_kwh"] = daily_mean_load_kwh
        metadata["annual_mean_load_kw"] = annual_mean_load_kw

        power_kw = float(decision.rated_power_kw)
        energy_kwh = float(decision.rated_energy_kwh)
        duration_h = float(decision.duration_h())

        metadata["candidate_power_kw"] = power_kw
        metadata["candidate_energy_kwh"] = energy_kwh
        metadata["candidate_duration_h"] = duration_h

        boundary = self._strategy_boundary(ctx, decision.strategy_id)
        if boundary is not None:
            boundary_power_max = self._float_or_none(boundary.get("power_max_kw"))
            boundary_energy_max = self._float_or_none(boundary.get("energy_max_kwh"))
            boundary_power_min = self._float_or_none(boundary.get("power_min_kw"))
            if boundary_power_min is not None:
                metadata["configuration_boundary_power_min_kw"] = boundary_power_min
            if boundary_power_max is not None:
                metadata["configuration_boundary_power_max_kw"] = boundary_power_max
                if power_kw > boundary_power_max + 1e-9:
                    return ScreeningResult(
                        is_feasible=False,
                        messages=[
                            f"候选功率 {power_kw:.2f}kW 超过由负荷特性/并网容量/变压器容量计算的配置边界 {boundary_power_max:.2f}kW。"
                        ],
                        metadata=metadata,
                    )
            if boundary_energy_max is not None:
                metadata["configuration_boundary_energy_max_kwh"] = boundary_energy_max
                if energy_kwh > boundary_energy_max + 1e-9:
                    return ScreeningResult(
                        is_feasible=False,
                        messages=[
                            f"候选容量 {energy_kwh:.2f}kWh 超过由负荷日用电量和可用SOC窗口计算的配置边界 {boundary_energy_max:.2f}kWh。"
                        ],
                        metadata=metadata,
                    )

        if boundary is None and peak_load_kw > 1e-9:
            power_to_peak = power_kw / peak_load_kw
            metadata["power_to_peak_load_ratio"] = power_to_peak

            if power_to_peak < float(cfg.min_power_to_peak_load_ratio):
                return ScreeningResult(
                    is_feasible=False,
                    messages=[f"候选功率仅为峰值负荷的 {power_to_peak:.4f}，低于下限 {cfg.min_power_to_peak_load_ratio:.4f}。"],
                    metadata=metadata,
                )

            if power_to_peak > float(cfg.max_power_to_peak_load_ratio):
                return ScreeningResult(
                    is_feasible=False,
                    messages=[f"候选功率为峰值负荷的 {power_to_peak:.4f}，高于上限 {cfg.max_power_to_peak_load_ratio:.4f}。"],
                    metadata=metadata,
                )

        transformer_limit = ctx.transformer_active_power_limit_kw
        if boundary is None and transformer_limit is not None and transformer_limit > 1e-9:
            ratio = power_kw / float(transformer_limit)
            metadata["power_to_transformer_limit_ratio"] = ratio
            if ratio > float(cfg.max_power_to_transformer_limit_ratio):
                return ScreeningResult(
                    is_feasible=False,
                    messages=[
                        f"候选功率与变压器有功上限比值为 {ratio:.4f}，高于粗筛上限 {cfg.max_power_to_transformer_limit_ratio:.4f}。"
                    ],
                    metadata=metadata,
                )

        if boundary is None and daily_mean_load_kwh > 1e-9:
            ratio_daily = energy_kwh / daily_mean_load_kwh
            metadata["energy_to_daily_mean_load_ratio"] = ratio_daily
            if ratio_daily > float(cfg.max_energy_to_daily_mean_load_ratio):
                return ScreeningResult(
                    is_feasible=False,
                    messages=[
                        f"候选容量与日均负荷电量比值为 {ratio_daily:.4f}，高于粗筛上限 {cfg.max_energy_to_daily_mean_load_ratio:.4f}。"
                    ],
                    metadata=metadata,
                )

        if boundary is None and annual_mean_load_kw > 1e-9:
            ratio_annual = energy_kwh / annual_mean_load_kw
            metadata["energy_to_annual_mean_load_ratio"] = ratio_annual
            if ratio_annual > float(cfg.max_energy_to_annual_mean_load_ratio):
                return ScreeningResult(
                    is_feasible=False,
                    messages=[
                        f"候选容量与年均负荷功率比值为 {ratio_annual:.4f}，高于粗筛上限 {cfg.max_energy_to_annual_mean_load_ratio:.4f}。"
                    ],
                    metadata=metadata,
                )

        if ctx.service_config.enable_service:
            metadata["service_enabled"] = True
            if (not strategy.allow_service) and (not cfg.allow_non_service_strategy_when_service_enabled):
                return ScreeningResult(
                    is_feasible=False,
                    messages=[f"当前为综合收益场景，但策略 {strategy.strategy_id} 不允许服务参与。"],
                    metadata=metadata,
                )

        if duration_h < float(strategy.duration_min_h) - float(cfg.duration_tolerance_h):
            return ScreeningResult(
                is_feasible=False,
                messages=[f"候选时长 {duration_h:.4f}h 低于粗筛下限。"],
                metadata=metadata,
            )
        if duration_h > float(strategy.duration_max_h) + float(cfg.duration_tolerance_h):
            return ScreeningResult(
                is_feasible=False,
                messages=[f"候选时长 {duration_h:.4f}h 高于粗筛上限。"],
                metadata=metadata,
            )

        score_hint = 0.0
        if peak_load_kw > 1e-9:
            score_hint += min(power_kw / peak_load_kw, 1.0)
        if daily_mean_load_kwh > 1e-9:
            score_hint += min(energy_kwh / daily_mean_load_kwh, 1.0)

        messages.append("通过快速筛选。")
        return ScreeningResult(
            is_feasible=True,
            messages=messages,
            score_hint=float(score_hint),
            metadata=metadata,
        )
