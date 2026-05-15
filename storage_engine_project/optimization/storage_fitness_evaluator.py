from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
import numpy as np

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.economics.lifecycle_financial_evaluator import (
    LifecycleFinancialConfig,
    LifecycleFinancialEvaluator,
)
from storage_engine_project.logging_config import get_logger
from storage_engine_project.optimization.candidate_screening import (
    CandidateScreeningConfig,
    CandidateScreeningEngine,
)
from storage_engine_project.optimization.optimization_models import (
    ConstraintVector,
    FitnessEvaluationResult,
    ObjectiveVector,
    ScreeningResult,
    StorageDecision,
)
from storage_engine_project.simulation.annual_operation_kernel import (
    AnnualOperationKernel,
    AnnualOperationKernelConfig,
)
from storage_engine_project.simulation.network_constraint_oracle import NetworkConstraintOracle

logger = get_logger(__name__)


@dataclass(slots=True)
class FitnessEvaluatorConfig:
    use_four_objectives: bool = True
    large_penalty_value: float = 1e12
    invalid_payback_proxy_years: float = 99.0

    max_allowed_payback_years: float | None = None
    require_positive_annual_cashflow: bool = False
    enforce_annual_cycle_limit: bool = True

    safety_objective_transformer_hours_weight: float = 10.0
    safety_objective_transformer_slack_weight: float = 1.0
    safety_objective_voltage_hours_weight: float = 10.0
    safety_objective_line_overload_hours_weight: float = 10.0
    safety_objective_cycle_weight: float = 1.0
    safety_objective_delta_safety_weight: float = 10.0

    # 改进#5: 结果缓存优化
    enable_result_cache: bool = True
    cache_max_size: int = 1000
    cache_hit_log: bool = False

    # 改进#2: 双阶段评估优化（fast_proxy仍使用OpenDSS）
    enable_dual_stage_evaluation: bool = True
    fast_proxy_day_stride: int = 14
    fast_proxy_selected_day_indices: tuple[int, ...] = tuple()
    keep_daily_objects_fast_proxy: bool = False

    run_full_recheck_for_every_candidate: bool = False
    full_recheck_for_fast_feasible_only: bool = True
    full_recheck_max_payback_years: float = 15.0
    full_recheck_min_npv_to_investment_ratio: float = -0.20
    full_recheck_require_non_negative_cashflow: bool = True
    prefer_opendss_in_full_recheck: bool = True

    # 改进#3: 并行评估
    enable_parallel_evaluation: bool = False
    max_workers: int = 4

    print_candidate_logs: bool = False
    print_screening_fail_logs: bool = True
    print_recheck_trigger_logs: bool = True
    print_candidate_finish_logs: bool = True


class StorageFitnessEvaluator:
    def __init__(
        self,
        annual_kernel: AnnualOperationKernel | None = None,
        financial_evaluator: LifecycleFinancialEvaluator | None = None,
        screening_engine: CandidateScreeningEngine | None = None,
        config: FitnessEvaluatorConfig | None = None,
    ) -> None:
        self.annual_kernel = annual_kernel or AnnualOperationKernel(
            config=AnnualOperationKernelConfig()
        )
        self.financial_evaluator = financial_evaluator or LifecycleFinancialEvaluator(
            config=LifecycleFinancialConfig()
        )
        self.screening_engine = screening_engine or CandidateScreeningEngine(
            config=CandidateScreeningConfig()
        )
        self.config = config or FitnessEvaluatorConfig()
        self._cache: OrderedDict[tuple, FitnessEvaluationResult] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0
        self._eval_counter = 0

    def _resolve_context_for_decision(
        self,
        ctx: AnnualOperationContext,
        decision: StorageDecision,
    ) -> AnnualOperationContext:
        if ctx.strategy.strategy_id == decision.strategy_id:
            return ctx
        return ctx.with_strategy(decision.strategy_id)

    def evaluate_decision(
        self,
        ctx: AnnualOperationContext,
        decision: StorageDecision,
        actual_load_matrix_kw: np.ndarray | None = None,
        actual_pv_matrix_kw: np.ndarray | None = None,
        network_oracle: NetworkConstraintOracle | None = None,
        force_full_recheck: bool = False,
    ) -> FitnessEvaluationResult:
        self._eval_counter += 1
        eval_no = self._eval_counter
        local_ctx = self._resolve_context_for_decision(ctx, decision)

        if self.config.print_candidate_logs:
            mode_label = "full_recheck" if force_full_recheck else ("fast_proxy" if self.config.enable_dual_stage_evaluation else "full_year")
            logger.info(
                "候选评估 #%s 开始 | 场景=%s | 策略=%s | P=%.2f kW | E=%.2f kWh | 时长=%.2f h | mode=%s",
                eval_no, local_ctx.internal_model_id, decision.strategy_id,
                decision.rated_power_kw, decision.rated_energy_kwh, decision.duration_h(), mode_label,
            )

        screening = self.screening_engine.screen(local_ctx, decision)
        if not screening.is_feasible:
            if self.config.print_screening_fail_logs:
                logger.debug("候选评估 #%s 快速筛选未通过：%s", eval_no, screening.reason_text)
            return self._build_fast_reject_result(decision, screening)

        if force_full_recheck:
            result = self._run_single_stage(
                eval_no=eval_no,
                ctx=local_ctx,
                decision=decision,
                annual_mode="full_recheck",
                actual_load_matrix_kw=actual_load_matrix_kw,
                actual_pv_matrix_kw=actual_pv_matrix_kw,
                network_oracle=network_oracle,
                screening=screening,
            )
            self._maybe_cache(result, local_ctx, decision, mode="full_recheck")
            return result

        if self.config.enable_dual_stage_evaluation:
            fast_result = self._run_single_stage(
                eval_no=eval_no,
                ctx=local_ctx,
                decision=decision,
                annual_mode="fast_proxy",
                actual_load_matrix_kw=actual_load_matrix_kw,
                actual_pv_matrix_kw=actual_pv_matrix_kw,
                network_oracle=network_oracle,
                screening=screening,
            )
            self._maybe_cache(fast_result, local_ctx, decision, mode="fast_proxy")

            if self._should_run_full_recheck(fast_result):
                if self.config.print_recheck_trigger_logs:
                    logger.info("候选评估 #%s 快评结果达到重校核条件，开始 full_recheck。", eval_no)
                full_result = self._run_single_stage(
                    eval_no=eval_no,
                    ctx=local_ctx,
                    decision=decision,
                    annual_mode="full_recheck",
                    actual_load_matrix_kw=actual_load_matrix_kw,
                    actual_pv_matrix_kw=actual_pv_matrix_kw,
                    network_oracle=network_oracle,
                    screening=screening,
                )
                self._append_unique_note(full_result, "已基于 fast_proxy 结果触发 full_recheck。")
                self._maybe_cache(full_result, local_ctx, decision, mode="full_recheck")
                return full_result

            return fast_result

        result = self._run_single_stage(
            eval_no=eval_no,
            ctx=local_ctx,
            decision=decision,
            annual_mode="full_year",
            actual_load_matrix_kw=actual_load_matrix_kw,
            actual_pv_matrix_kw=actual_pv_matrix_kw,
            network_oracle=network_oracle,
            screening=screening,
        )
        self._maybe_cache(result, local_ctx, decision, mode="full_year")
        return result

    def _run_single_stage(
        self,
        eval_no: int,
        ctx: AnnualOperationContext,
        decision: StorageDecision,
        annual_mode: str,
        actual_load_matrix_kw: np.ndarray | None,
        actual_pv_matrix_kw: np.ndarray | None,
        network_oracle: NetworkConstraintOracle | None,
        screening: ScreeningResult,
    ) -> FitnessEvaluationResult:
        oracle_scope = self._network_oracle_cache_scope(network_oracle)
        cache_key = (
            str(ctx.internal_model_id),
            str(decision.strategy_id),
            round(float(decision.rated_power_kw), 6),
            round(float(decision.rated_energy_kwh), 6),
            annual_mode,
            oracle_scope,
        )
        if self.config.enable_result_cache and cache_key in self._cache:
            self._cache_hits += 1
            if self.config.cache_hit_log:
                logger.debug("缓存命中 eval_no=%s, key=%s", eval_no, cache_key[:3])
            self._cache.move_to_end(cache_key)
            return self._clone_result(self._cache[cache_key])
        
        if self.config.enable_result_cache:
            self._cache_misses += 1

        annual_result = self.annual_kernel.run_year(
            ctx=ctx,
            rated_power_kw=float(decision.rated_power_kw),
            rated_energy_kwh=float(decision.rated_energy_kwh),
            actual_load_matrix_kw=actual_load_matrix_kw,
            actual_pv_matrix_kw=actual_pv_matrix_kw,
            network_oracle=network_oracle,
            evaluation_mode=annual_mode,
            fast_proxy_day_stride=self.config.fast_proxy_day_stride,
            fast_proxy_selected_day_indices=self.config.fast_proxy_selected_day_indices,
            keep_daily_objects=(False if annual_mode == "fast_proxy" else True),
        )

        financial_result = self.financial_evaluator.evaluate(
            ctx=ctx,
            annual_result=annual_result,
        )

        objective_vector = self._build_objective_vector(
            annual_result=annual_result,
            financial_result=financial_result,
        )
        constraint_vector = self._build_constraint_vector(
            ctx=ctx,
            decision=decision,
            annual_result=annual_result,
            financial_result=financial_result,
        )

        result = FitnessEvaluationResult(
            decision=decision,
            screening_result=screening,
            objective_vector=objective_vector,
            constraint_vector=constraint_vector,
            annual_operation_result=annual_result,
            lifecycle_financial_result=financial_result,
            is_valid=True,
            used_fast_reject=False,
            notes=[f"已完成 {annual_mode} 年度运行与生命周期财务评价。"],
            metadata={
                "cache_key": cache_key,
                "network_oracle_scope": oracle_scope,
                "recheck_performed": bool(annual_mode == "full_recheck"),
            },
        )
        self._dedupe_notes(result)

        if self.config.print_candidate_finish_logs:
            logger.info(
                "候选评估 #%s 完成 | NPV=%.2f | Payback=%s | Cycles=%.2f | mode=%s",
                eval_no, financial_result.npv_yuan, financial_result.simple_payback_years,
                annual_result.annual_equivalent_full_cycles, annual_mode,
            )

        return result

    def _should_run_full_recheck(self, fast_result: FitnessEvaluationResult) -> bool:
        cfg = self.config
        if cfg.run_full_recheck_for_every_candidate:
            return True
        if not cfg.full_recheck_for_fast_feasible_only:
            return False
        if fast_result.lifecycle_financial_result is None or fast_result.annual_operation_result is None:
            return False

        fr = fast_result.lifecycle_financial_result
        ar = fast_result.annual_operation_result
        payback = fr.simple_payback_years
        if payback is None or float(payback) > float(cfg.full_recheck_max_payback_years):
            return False
        invest = max(float(fr.initial_investment_yuan), 1.0)
        npv_ratio = float(fr.npv_yuan) / invest
        if npv_ratio < float(cfg.full_recheck_min_npv_to_investment_ratio):
            return False
        if cfg.full_recheck_require_non_negative_cashflow and float(ar.annual_net_operating_cashflow_yuan) < 0.0:
            return False
        return True

    def _maybe_cache(
        self,
        result: FitnessEvaluationResult,
        ctx: AnnualOperationContext,
        decision: StorageDecision,
        mode: str,
    ) -> None:
        if not self.config.enable_result_cache:
            return
        key = result.metadata.get("cache_key") if isinstance(result.metadata, dict) else None
        if not isinstance(key, tuple):
            key = (
                str(ctx.internal_model_id),
                str(decision.strategy_id),
                round(float(decision.rated_power_kw), 6),
                round(float(decision.rated_energy_kwh), 6),
                mode,
                "network_oracle:none",
            )
        
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = self._clone_result(result)
            if len(self._cache) > self.config.cache_max_size:
                self._cache.popitem(last=False)

    @staticmethod
    def _clone_result(result: FitnessEvaluationResult) -> FitnessEvaluationResult:
        return deepcopy(result)

    @staticmethod
    def _network_oracle_cache_scope(network_oracle: NetworkConstraintOracle | None) -> str:
        if network_oracle is None:
            return "network_oracle:none"
        cls = network_oracle.__class__
        return f"network_oracle:{cls.__module__}.{cls.__name__}"

    @staticmethod
    def _append_unique_note(result: FitnessEvaluationResult, note: str) -> None:
        if note not in result.notes:
            result.notes.insert(0, note)

    @staticmethod
    def _dedupe_notes(result: FitnessEvaluationResult) -> None:
        deduped: list[str] = []
        for note in result.notes:
            if note not in deduped:
                deduped.append(note)
        result.notes = deduped

    def _build_fast_reject_result(
        self,
        decision: StorageDecision,
        screening: ScreeningResult,
    ) -> FitnessEvaluationResult:
        penalty = float(self.config.large_penalty_value)
        objective_vector = ObjectiveVector(
            obj_npv=penalty,
            obj_payback=float(self.config.invalid_payback_proxy_years),
            obj_investment=penalty,
            obj_safety=penalty if self.config.use_four_objectives else 0.0,
        )
        constraint_vector = ConstraintVector(
            duration_violation_h=1.0,
            cycle_violation=0.0,
            transformer_violation_hours=0.0,
            transformer_slack_kw=0.0,
            voltage_violation_pu=0.0,
            line_loading_violation_pct=0.0,
            negative_cashflow_violation=1.0,
            payback_violation_years=1.0,
        )
        return FitnessEvaluationResult(
            decision=decision,
            screening_result=screening,
            objective_vector=objective_vector,
            constraint_vector=constraint_vector,
            annual_operation_result=None,
            lifecycle_financial_result=None,
            is_valid=False,
            used_fast_reject=True,
            notes=["候选方案在快速筛选阶段被拒绝。"],
        )

    def _build_objective_vector(self, annual_result, financial_result) -> ObjectiveVector:
        cfg = self.config
        metadata = annual_result.metadata if isinstance(getattr(annual_result, "metadata", None), dict) else {}
        npv = float(financial_result.npv_yuan)
        payback = (
            float(financial_result.simple_payback_years)
            if financial_result.simple_payback_years is not None
            else float(cfg.invalid_payback_proxy_years)
        )
        investment = float(financial_result.initial_investment_yuan)
        voltage_hours = metadata.get("target_hours_with_voltage_violation")
        if voltage_hours is None:
            voltage_hours = metadata.get("hours_with_voltage_violation", 0.0)
        line_overload_hours = metadata.get("target_hours_with_line_overload")
        if line_overload_hours is None:
            line_overload_hours = metadata.get("hours_with_line_overload", 0.0)
        delta_safety_hours = metadata.get("delta_target_safety_violation_hours")
        if delta_safety_hours is None:
            delta_safety_hours = metadata.get("delta_safety_violation_hours", 0.0)

        safety_proxy = (
            float(annual_result.transformer_violation_hours) * float(cfg.safety_objective_transformer_hours_weight)
            + float(annual_result.max_transformer_slack_kw) * float(cfg.safety_objective_transformer_slack_weight)
            + float(voltage_hours) * float(cfg.safety_objective_voltage_hours_weight)
            + float(line_overload_hours) * float(cfg.safety_objective_line_overload_hours_weight)
            + float(annual_result.annual_equivalent_full_cycles) * float(cfg.safety_objective_cycle_weight)
            - float(delta_safety_hours) * float(cfg.safety_objective_delta_safety_weight)
        )

        return ObjectiveVector(
            obj_npv=-npv,
            obj_payback=payback,
            obj_investment=investment,
            obj_safety=safety_proxy if cfg.use_four_objectives else 0.0,
        )

    def _build_constraint_vector(self, ctx: AnnualOperationContext, decision: StorageDecision, annual_result, financial_result) -> ConstraintVector:
        strategy = ctx.strategy
        cfg = self.config
        metadata = annual_result.metadata if isinstance(getattr(annual_result, "metadata", None), dict) else {}

        duration = float(decision.duration_h())
        duration_violation = 0.0
        if duration < float(strategy.duration_min_h):
            duration_violation = float(strategy.duration_min_h) - duration
        elif duration > float(strategy.duration_max_h):
            duration_violation = duration - float(strategy.duration_max_h)

        cycle_violation = 0.0
        if cfg.enforce_annual_cycle_limit and float(strategy.annual_cycle_limit) > 0.0:
            cycle_violation = max(0.0, float(annual_result.annual_equivalent_full_cycles) - float(strategy.annual_cycle_limit))

        negative_cashflow_violation = 0.0
        if cfg.require_positive_annual_cashflow:
            negative_cashflow_violation = max(0.0, -float(annual_result.annual_net_operating_cashflow_yuan))

        payback_violation = 0.0
        if cfg.max_allowed_payback_years is not None:
            pb = financial_result.simple_payback_years
            if pb is None:
                payback_violation = float(cfg.max_allowed_payback_years)
            else:
                payback_violation = max(0.0, float(pb) - float(cfg.max_allowed_payback_years))

        if metadata.get("max_target_voltage_violation_pu") is not None:
            voltage_violation = self._nonnegative_metric(metadata.get("max_target_voltage_violation_pu"))
        else:
            voltage_violation = self._nonnegative_metric(metadata.get("max_voltage_violation_pu"))

        if metadata.get("max_target_line_overload_pct") is not None:
            line_loading_violation = self._nonnegative_metric(metadata.get("max_target_line_overload_pct"))
        elif metadata.get("max_target_line_loading_pct") is not None:
            line_loading_violation = max(0.0, self._nonnegative_metric(metadata.get("max_target_line_loading_pct")) - 100.0)
        else:
            line_loading_violation = self._nonnegative_metric(metadata.get("max_line_overload_pct"))
            if line_loading_violation <= 0.0:
                line_loading_violation = max(0.0, self._nonnegative_metric(metadata.get("max_line_loading_pct")) - 100.0)

        return ConstraintVector(
            duration_violation_h=float(duration_violation),
            cycle_violation=float(cycle_violation),
            transformer_violation_hours=float(max(0.0, annual_result.transformer_violation_hours)),
            transformer_slack_kw=float(max(0.0, annual_result.max_transformer_slack_kw)),
            voltage_violation_pu=float(voltage_violation),
            line_loading_violation_pct=float(line_loading_violation),
            negative_cashflow_violation=float(negative_cashflow_violation),
            payback_violation_years=float(payback_violation),
        )

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
    
    def get_cache_stats(self) -> dict[str, int]:
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
        }

    @staticmethod
    def _nonnegative_metric(value: object) -> float:
        try:
            if value in (None, ""):
                return 0.0
            parsed = float(value)
        except Exception:
            return 0.0
        if not np.isfinite(parsed):
            return 0.0
        return max(0.0, float(parsed))
