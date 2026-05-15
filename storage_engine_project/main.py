from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from storage_engine_project.logging_config import get_logger

logger = get_logger(__name__)

if __name__ == "__main__":
    _parent = Path(__file__).resolve().parent.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))

from storage_engine_project.config.operation_config import OperationConfig
from storage_engine_project.config.safety_config import SafetyConfig
from storage_engine_project.config.service_config import ServiceConfig
from storage_engine_project.data.case_builder import load_optimization_cases
from storage_engine_project.optimization.lemming_optimizer import (
    LemmingOptimizationRunResult,
    LemmingOptimizer,
    LemmingOptimizerConfig,
)
from storage_engine_project.optimization.optimization_models import FitnessEvaluationResult
from storage_engine_project.optimization.optimizer_bridge import OptimizerBridge
from storage_engine_project.optimization.storage_fitness_evaluator import (
    FitnessEvaluatorConfig,
    StorageFitnessEvaluator,
)
from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationKernel, AnnualOperationKernelConfig
from storage_engine_project.simulation.day_ahead_scheduler import DayAheadScheduler, DayAheadSchedulerConfig
from storage_engine_project.simulation.rolling_dispatch import RollingDispatchController, RollingDispatchConfig
from storage_engine_project.utils.result_exporter import export_optimization_run

try:
    from storage_engine_project.simulation.opendss_network_constraint_oracle import (
        OpenDSSConstraintOracle,
        OpenDSSOracleConfig,
    )
except Exception:  # pragma: no cover
    OpenDSSConstraintOracle = None
    OpenDSSOracleConfig = None


def _env_str(name: str, default: str = "") -> str:
    val = os.getenv(name, default)
    return str(val) if val is not None else str(default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _clamp_float(value: Any, default: float, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if not math.isfinite(parsed):
        parsed = float(default)
    return float(min(max(parsed, lower), upper))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="工商业配储年度优化整合版主程序")
    parser.add_argument("--registry", type=str, default="inputs/registry/node_registry.xlsx", help="场景注册表路径")
    parser.add_argument("--strategy-library", type=str, default="inputs/storage/工商业储能设备策略库.xlsx", help="储能设备策略库路径")
    parser.add_argument("--target-id", type=str, default="", help="仅运行指定 internal_model_id；为空则跑所有启用场景")
    parser.add_argument("--output-dir", type=str, default="outputs/integrated_optimization", help="结果输出目录")
    parser.add_argument("--population-size", type=int, default=16, help="种群规模")
    parser.add_argument("--generations", type=int, default=8, help="优化代数")
    parser.add_argument("--disable-plots", action="store_true", help="不生成绘图文件")
    parser.add_argument("--safety-economy-tradeoff", type=float, default=0.5, help="安全-经济权衡系数：0=纯经济最优，1=纯安全最优（默认 0.5 并重）")
    parser.add_argument("--initial-soc", type=float, default=_env_float("STORAGE_INITIAL_SOC", 0.50), help="年度仿真的首日初始 SOC")
    parser.add_argument("--terminal-soc-mode", type=str, default=_env_str("STORAGE_TERMINAL_SOC_MODE", "weekly_anchor"), help="日末 SOC 目标模式：free/carry/fixed/strategy_mid/weekly_anchor")
    parser.add_argument("--fixed-terminal-soc-target", type=float, default=_env_float("STORAGE_FIXED_TERMINAL_SOC_TARGET", 0.50), help="fixed 模式下每日末端 SOC 目标")
    parser.add_argument("--daily-terminal-soc-tolerance", type=float, default=_env_float("STORAGE_DAILY_TERMINAL_SOC_TOLERANCE", 0.02), help="每日末端 SOC 允许偏差")

    # 改进#6: OpenDSS网络约束集成（强制启用）
    parser.add_argument("--enable-opendss-oracle", action="store_true", default=_env_bool("STORAGE_ENABLE_OPENDSS_ORACLE", True), help="启用 OpenDSS 约束 oracle（生产环境强制）")
    parser.add_argument("--dss-master-path", type=str, default=_env_str("STORAGE_OPENDSS_MASTER_PATH", _env_str("STORAGE_DSS_MASTER", "")), help="OpenDSS Master.dss 路径")
    parser.add_argument("--dss-engine", type=str, default=_env_str("STORAGE_OPENDSS_ENGINE", "auto"), help="OpenDSS 引擎偏好：auto/com")
    parser.add_argument("--opendss-target-bus", type=str, default=_env_str("STORAGE_OPENDSS_TARGET_BUS", ""), help="储能接入目标母线名")
    parser.add_argument("--opendss-target-load", type=str, default=_env_str("STORAGE_OPENDSS_TARGET_LOAD", ""), help="目标负荷元件名")
    parser.add_argument("--opendss-bus-kv-ln", type=float, default=_env_float("STORAGE_OPENDSS_BUS_KV_LN", 10.0), help="目标母线基准电压 kV（三相模型按线电压）")
    parser.add_argument("--opendss-vmin-pu", type=float, default=_env_float("STORAGE_OPENDSS_VMIN_PU", 0.93), help="电压下限 pu")
    parser.add_argument("--opendss-vmax-pu", type=float, default=_env_float("STORAGE_OPENDSS_VMAX_PU", 1.07), help="电压上限 pu")
    parser.add_argument("--opendss-voltage-penalty-coeff", type=float, default=_env_float("STORAGE_OPENDSS_VOLTAGE_PENALTY_COEFF", 0.0), help="电压越限罚金系数 元/pu")
    parser.add_argument("--opendss-only-for-full-recheck", action="store_true", default=_env_bool("STORAGE_OPENDSS_ONLY_FOR_FULL_RECHECK", False), help="兼容旧模式：仅在 full_recheck 阶段使用 OpenDSS（不推荐）")
    parser.add_argument("--prefer-opendss-in-full-recheck", action="store_true", default=_env_bool("STORAGE_OPENDSS_PREFER_FULL_RECHECK", True), help="在 dual-stage 中偏好 OpenDSS full_recheck")
    return parser.parse_args()


def build_global_configs(args: argparse.Namespace | None = None) -> tuple[OperationConfig, SafetyConfig, ServiceConfig]:
    """改进#10: 配置验证强化"""
    allowed_terminal_modes = {"free", "carry", "fixed", "strategy_mid", "weekly_anchor", "monthly_anchor", "blended_anchor"}
    terminal_soc_mode = str(getattr(args, "terminal_soc_mode", "weekly_anchor")).strip().lower() or "weekly_anchor"
    if terminal_soc_mode not in allowed_terminal_modes:
        logger.warning("无效的terminal_soc_mode '%s'，使用默认值 'weekly_anchor'", terminal_soc_mode)
        terminal_soc_mode = "weekly_anchor"
    
    initial_soc = _clamp_float(getattr(args, "initial_soc", 0.50), 0.50, 0.0, 1.0)
    if initial_soc < 0.1 or initial_soc > 0.9:
        logger.warning("initial_soc=%.3f 超出推荐范围[0.1, 0.9]", initial_soc)
    
    fixed_terminal_soc_target = _clamp_float(getattr(args, "fixed_terminal_soc_target", 0.50), 0.50, 0.0, 1.0)
    daily_terminal_soc_tolerance = _clamp_float(getattr(args, "daily_terminal_soc_tolerance", 0.02), 0.02, 0.0, 0.20)
    
    if daily_terminal_soc_tolerance > 0.10:
        logger.warning("daily_terminal_soc_tolerance=%.3f 过大，可能影响优化质量", daily_terminal_soc_tolerance)
    
    enforce_daily_terminal_soc = terminal_soc_mode != "free"
    enable_terminal_soc_correction = terminal_soc_mode != "free"

    operation_config = OperationConfig(
        annual_days=365,
        hours_per_day=24,
        day_ahead_step_hours=1,
        rolling_step_minutes=60,
        use_rolling_dispatch=True,
        enforce_daily_terminal_soc=enforce_daily_terminal_soc,
        daily_terminal_soc_tolerance=daily_terminal_soc_tolerance,
        terminal_soc_mode=terminal_soc_mode,
        fixed_terminal_soc_target=fixed_terminal_soc_target,
        anchor_soc_target=fixed_terminal_soc_target,
        anchor_cycle_days=7,
        anchor_day_index=6,
        interday_soc_reversion_weight=0.35,
        enable_terminal_soc_correction=enable_terminal_soc_correction,
        terminal_soc_correction_hours=4,
        enable_transformer_limit=True,
        enable_voltage_penalty=True,
        use_network_oracle=True,
        network_recheck_interval_hours=1,
        fast_screen_mode=False,
        debug=False,
    )
    
    # 改进#10: 配置一致性检查
    if not operation_config.use_rolling_dispatch:
        logger.warning("use_rolling_dispatch=False 可能导致实时约束无法正确处理")
    if not operation_config.enable_transformer_limit:
        logger.warning("enable_transformer_limit=False 将忽略变压器容量约束")

    safety_config = SafetyConfig(
        global_soc_margin=0.01,
        derate_high=0.90,
        derate_medium=0.95,
        derate_low=1.00,
        enforce_strategy_soc_window=True,
        enforce_strategy_temperature_window=True,
        allow_fallback_defaults=True,
        annual_cycle_soft_cap_ratio=1.00,
        temperature_proxy_penalty_yuan_per_deg_hour=0.0,
        allow_grid_charging_default=True,
        min_service_headroom_ratio=0.05,
    )

    service_config = ServiceConfig(
        enable_service=False,
        scenario_name="arbitrage_only",
        service_mode="none",
        default_available_hours=tuple(),
        default_capacity_price_yuan_per_kw=0.0,
        default_delivery_price_yuan_per_kwh=0.0,
        default_penalty_price_yuan_per_kwh=0.0,
        default_activation_factor=0.0,
        max_service_power_ratio=0.0,
        require_headroom=False,
        default_headroom_ratio=0.0,
        delivery_score_floor=1.0,
    )
    return operation_config, safety_config, service_config


def _build_network_oracle(args: argparse.Namespace):
    if not bool(args.enable_opendss_oracle):
        return None
    if OpenDSSConstraintOracle is None or OpenDSSOracleConfig is None:
        raise RuntimeError("已请求启用 OpenDSS oracle，但未能导入 OpenDSS oracle 模块。")
    if not str(args.dss_master_path).strip():
        raise RuntimeError("已请求启用 OpenDSS oracle，但未提供 Master.dss 路径。")

    cfg = OpenDSSOracleConfig(
        master_dss_path=str(args.dss_master_path),
        target_bus_name=str(args.opendss_target_bus).strip() or None,
        target_load_name=str(args.opendss_target_load).strip() or None,
        target_kv_ln=float(args.opendss_bus_kv_ln),
        engine_preference=str(args.dss_engine).strip() or "auto",
        voltage_min_pu=float(args.opendss_vmin_pu),
        voltage_max_pu=float(args.opendss_vmax_pu),
        voltage_penalty_coeff_yuan_per_pu=float(args.opendss_voltage_penalty_coeff),
        compile_each_call=True,
        allow_engine_fallback=False,
        log_failures=True,
    )
    try:
        oracle = OpenDSSConstraintOracle(config=cfg)
        logger.info("已启用 OpenDSS oracle，Master=%s", args.dss_master_path)
        return oracle
    except Exception as exc:
        raise RuntimeError(
            "OpenDSS oracle 初始化失败，无法执行真实潮流仿真。"
            "请确认已安装 OpenDSS，并在 storage_engine_project\\.venv 中安装 pywin32，使 Python 可导入 win32com.client。"
            f"原始错误：{type(exc).__name__}: {exc}"
        ) from exc


def _build_evaluator(args: argparse.Namespace) -> StorageFitnessEvaluator:
    scheduler = DayAheadScheduler(
        config=DayAheadSchedulerConfig(
            preferred_solvers=("ECOS", "SCS"),
            allow_fallback_rule=True,
            validate_candidate_before_solve=True,
            enable_plan_cache=True,
            log_input_signature=False,
            log_cache_hit=False,
            log_solver_success=False,
            log_solver_failure=True,
            log_solver_inaccurate=True,
            print_solver_order=False,
            prefer_solver_order_when_status_ties=True,
        )
    )
    rolling = RollingDispatchController(
        config=RollingDispatchConfig(
            transformer_violation_penalty_yuan_per_kwh=300.0,
            degradation_weight_service=1.0,
            allow_service_curtailment=True,
            safety_first=True,
            enforce_soc_hard_clip=True,
            net_power_execution_mode=True,
            enable_terminal_soc_correction=True,
            terminal_soc_correction_hours=4,
            terminal_soc_correction_max_fraction_of_power=0.70,
        )
    )
    kernel = AnnualOperationKernel(
        scheduler=scheduler,
        rolling_controller=rolling,
        config=AnnualOperationKernelConfig(
            initial_soc=_clamp_float(getattr(args, "initial_soc", 0.50), 0.50, 0.0, 1.0),
            use_actual_matrices_for_rolling=True,
            monthly_demand_charge_yuan_per_kw=0.0,
            annual_start_date="2025-01-01",
            keep_daily_objects=True,
            load_round_ndigits=3,
            tariff_round_ndigits=4,
            compress_fast_proxy_groups=True,
            print_mode_header=True,
            print_progress=True,
            progress_interval_days=30,
            fast_proxy_progress_interval_groups=5,
            print_completion_summary=True,
        ),
    )
    return StorageFitnessEvaluator(
        annual_kernel=kernel,
        config=FitnessEvaluatorConfig(
            use_four_objectives=True,
            large_penalty_value=1e12,
            invalid_payback_proxy_years=99.0,
            max_allowed_payback_years=None,
            require_positive_annual_cashflow=False,
            enforce_annual_cycle_limit=True,
            safety_objective_transformer_hours_weight=10.0,
            safety_objective_transformer_slack_weight=1.0,
            safety_objective_cycle_weight=1.0,
            enable_result_cache=True,
            enable_dual_stage_evaluation=True,
            fast_proxy_day_stride=14,
            fast_proxy_selected_day_indices=tuple(),
            keep_daily_objects_fast_proxy=False,
            run_full_recheck_for_every_candidate=False,
            full_recheck_for_fast_feasible_only=True,
            full_recheck_max_payback_years=15.0,
            full_recheck_min_npv_to_investment_ratio=-0.10,
            full_recheck_require_non_negative_cashflow=False,
            prefer_opendss_in_full_recheck=bool(args.prefer_opendss_in_full_recheck),
            print_candidate_logs=False,
            print_screening_fail_logs=True,
            print_recheck_trigger_logs=True,
            print_candidate_finish_logs=True,
        ),
    )


def _replace_same_decision(results: list[FitnessEvaluationResult], new_result: FitnessEvaluationResult) -> list[FitnessEvaluationResult]:
    out: list[FitnessEvaluationResult] = []
    for item in results:
        d0 = item.decision
        d1 = new_result.decision
        same = (
            d0.strategy_id == d1.strategy_id
            and abs(float(d0.rated_power_kw) - float(d1.rated_power_kw)) <= 1e-9
            and abs(float(d0.rated_energy_kwh) - float(d1.rated_energy_kwh)) <= 1e-9
        )
        out.append(new_result if same else item)
    return out


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _opendss_trace_stats(annual_result: Any) -> dict[str, int]:
    stats = {
        "daily_exec_count": 0,
        "trace_count": 0,
        "opendss_trace_count": 0,
        "scalar_value_trace_count": 0,
        "bus_voltage_rows": 0,
        "line_current_rows": 0,
        "loss_trace_count": 0,
    }
    for exec_result in getattr(annual_result, "daily_exec_objects", None) or []:
        stats["daily_exec_count"] += 1
        for trace in getattr(exec_result, "network_trace", None) or []:
            if not isinstance(trace, dict):
                continue
            stats["trace_count"] += 1
            if not bool(trace.get("opendss_used", False)):
                continue
            stats["opendss_trace_count"] += 1
            has_scalar_values = any(
                _has_value(trace.get(key))
                for key in (
                    "voltage_pu_min",
                    "voltage_pu_max",
                    "line_current_max_a",
                    "line_loading_max_pct",
                )
            )
            has_loss_values = any(
                _has_value(trace.get(key))
                for key in (
                    "opendss_loss_baseline_kw",
                    "opendss_loss_with_storage_kw",
                    "opendss_loss_reduction_kwh",
                )
            )
            if has_scalar_values or has_loss_values:
                stats["scalar_value_trace_count"] += 1
            if has_loss_values:
                stats["loss_trace_count"] += 1
            for row in trace.get("bus_voltages") or []:
                if isinstance(row, dict) and (
                    _has_value(row.get("voltage_pu_min")) or _has_value(row.get("voltage_pu_max"))
                ):
                    stats["bus_voltage_rows"] += 1
            for row in trace.get("line_currents") or []:
                if isinstance(row, dict) and (
                    _has_value(row.get("current_a")) or _has_value(row.get("loading_pct"))
                ):
                    stats["line_current_rows"] += 1
    return stats


def _has_opendss_export_values(stats: dict[str, int]) -> bool:
    return (
        int(stats.get("opendss_trace_count", 0)) > 0
        and int(stats.get("scalar_value_trace_count", 0)) > 0
        and int(stats.get("bus_voltage_rows", 0)) > 0
        and int(stats.get("line_current_rows", 0)) > 0
    )


def _ensure_best_full_recheck(
    evaluator: StorageFitnessEvaluator,
    opt_case: Any,
    run_result: LemmingOptimizationRunResult,
    network_oracle=None,
) -> None:
    best = run_result.best_result
    if best is None:
        return

    meta = getattr(best, "metadata", {}) or {}
    ann = getattr(best, "annual_operation_result", None)
    rechecked_already = bool(meta.get("recheck_performed", False)) and ann is not None and getattr(ann, "evaluation_mode", "") == "full_recheck"
    trace_stats = _opendss_trace_stats(ann)
    if network_oracle is None:
        if rechecked_already:
            return
        logger.info("对最终折中解执行全年重校核...")
    else:
        if rechecked_already and _has_opendss_export_values(trace_stats):
            logger.info(
                "  最终折中解已包含 OpenDSS 网络计算值："
                "trace=%d，"
                "母线电压记录=%d，"
                "线路电流记录=%d。",
                trace_stats['opendss_trace_count'],
                trace_stats['bus_voltage_rows'],
                trace_stats['line_current_rows'],
            )
            return
        logger.info("调用 OpenDSS oracle 对最终折中解执行全年重校核...")

    rechecked = evaluator.evaluate_decision(
        ctx=opt_case.context,
        decision=best.decision,
        network_oracle=network_oracle,
        force_full_recheck=True,
    )
    rechecked_ann = getattr(rechecked, "annual_operation_result", None)
    rechecked_stats = _opendss_trace_stats(rechecked_ann)
    if isinstance(getattr(rechecked, "metadata", None), dict):
        rechecked.metadata["opendss_trace_stats"] = rechecked_stats
    if network_oracle is not None:
        logger.info(
            "  OpenDSS 重校核返回："
            "trace=%d，"
            "母线电压记录=%d，"
            "线路电流记录=%d，"
            "网损记录=%d。",
            rechecked_stats['opendss_trace_count'],
            rechecked_stats['bus_voltage_rows'],
            rechecked_stats['line_current_rows'],
            rechecked_stats['loss_trace_count'],
        )
        if not _has_opendss_export_values(rechecked_stats):
            raise RuntimeError(
                "OpenDSS oracle 已启用，但最终重校核没有返回可导出的母线电压和线路电流计算值；"
                "请检查 OpenDSS 模型、线路元件、母线命名与运行时负荷清单。"
            )
    run_result.best_result = rechecked
    run_result.archive_results = _replace_same_decision(run_result.archive_results, rechecked)
    run_result.population_results = _replace_same_decision(run_result.population_results, rechecked)


def _best_summary_row(opt_case: Any, run_result: LemmingOptimizationRunResult) -> dict[str, Any] | None:
    best = run_result.best_result
    if best is None:
        return None
    summary = best.summary_dict()
    ann = getattr(best, "annual_operation_result", None)
    fin = getattr(best, "lifecycle_financial_result", None)
    ann_meta = getattr(ann, "metadata", {}) or {}
    return {
        "internal_model_id": opt_case.internal_model_id,
        "scenario_name": getattr(opt_case.registry_scenario, "scenario_name", opt_case.internal_model_id),
        "node_id": getattr(opt_case.registry_scenario, "node_id", None),
        "strategy_id": summary.get("strategy_id"),
        "strategy_name": summary.get("strategy_name"),
        "rated_power_kw": summary.get("rated_power_kw"),
        "rated_energy_kwh": summary.get("rated_energy_kwh"),
        "duration_h": summary.get("duration_h"),
        "npv_yuan": summary.get("npv_yuan"),
        "simple_payback_years": summary.get("simple_payback_years"),
        "discounted_payback_years": summary.get("discounted_payback_years"),
        "irr": summary.get("irr"),
        "initial_investment_yuan": summary.get("initial_investment_yuan"),
        "government_subsidy_yuan": summary.get("government_subsidy_yuan"),
        "initial_net_investment_yuan": summary.get("initial_net_investment_yuan"),
        "annualized_net_cashflow_yuan": summary.get("annualized_net_cashflow_yuan"),
        "annual_net_operating_cashflow_yuan": summary.get("annual_net_operating_cashflow_yuan"),
        "annual_auxiliary_service_revenue_yuan": summary.get("annual_auxiliary_service_revenue_yuan"),
        "annual_capacity_revenue_yuan": summary.get("annual_capacity_revenue_yuan"),
        "annual_loss_reduction_revenue_yuan": summary.get("annual_loss_reduction_revenue_yuan"),
        "annual_demand_saving_yuan": summary.get("annual_demand_saving_yuan"),
        "annual_degradation_cost_yuan": summary.get("annual_degradation_cost_yuan"),
        "annual_om_cost_yuan": summary.get("annual_om_cost_yuan"),
        "annual_replacement_equivalent_cost_yuan": summary.get("annual_replacement_equivalent_cost_yuan"),
        "total_replacement_cost_yuan": summary.get("total_replacement_cost_yuan"),
        "annual_equivalent_full_cycles": summary.get("annual_equivalent_full_cycles"),
        "transformer_violation_hours": summary.get("transformer_violation_hours_runtime", summary.get("transformer_violation_hours")),
        "max_transformer_slack_kw": summary.get("max_transformer_slack_kw_runtime", summary.get("max_transformer_slack_kw")),
        "evaluation_mode": getattr(ann, "evaluation_mode", ""),
        "soc_start": getattr(ann, "soc_daily_open", [None])[0] if ann is not None else None,
        "soc_end": getattr(ann, "soc_daily_close", [None])[-1] if ann is not None else None,
        "mean_terminal_soc_error": ann_meta.get("mean_terminal_soc_error"),
        "mean_terminal_soc_error_before_correction": ann_meta.get("mean_terminal_soc_error_before_correction"),
        "terminal_correction_energy_kwh_total": ann_meta.get("terminal_correction_energy_kwh_total"),
        "target_anchor_hit_ratio": ann_meta.get("target_anchor_hit_ratio"),
        "project_life_years": getattr(fin, "project_life_years", None),
    }


def _build_engine_diagnostics(
    opt_case: Any,
    run_result: LemmingOptimizationRunResult,
    evaluator: StorageFitnessEvaluator,
) -> dict[str, Any]:
    """收集引擎运行期诊断信息（约束分层、缓存命中、自适应种群历史）。"""
    cache_stats: dict[str, Any] = {}
    try:
        cache_stats = evaluator.get_cache_stats() or {}
    except Exception:
        cache_stats = {}

    constraint_breakdown: dict[str, Any] = {}
    best = getattr(run_result, "best_result", None)
    cv = getattr(best, "constraint_vector", None) if best is not None else None
    if cv is not None:
        try:
            constraint_breakdown["hard"] = float(cv.hard_constraint_violation())
        except Exception:
            constraint_breakdown["hard"] = None
        try:
            constraint_breakdown["medium"] = float(cv.medium_constraint_violation())
        except Exception:
            constraint_breakdown["medium"] = None
        try:
            constraint_breakdown["soft"] = float(cv.soft_constraint_violation())
        except Exception:
            constraint_breakdown["soft"] = None
        try:
            raw = cv.as_dict() if hasattr(cv, "as_dict") else {}
            if isinstance(raw, dict):
                constraint_breakdown["raw"] = raw
        except Exception:
            pass

    history_raw = list(getattr(run_result, "history", None) or [])
    population_history: list[dict[str, Any]] = []
    for rec in history_raw:
        if isinstance(rec, dict):
            population_history.append({k: rec.get(k) for k in (
                "generation",
                "population_size",
                "feasible_count",
                "archive_size",
                "best_npv_yuan",
            ) if k in rec})

    return {
        "scenario": getattr(opt_case, "internal_model_id", None),
        "cache_stats": cache_stats,
        "constraint_breakdown": constraint_breakdown,
        "population_history": population_history,
    }


def run_one_case(
    opt_case: Any,
    output_root: Path,
    population_size: int,
    generations: int,
    generate_plots: bool = True,
    network_oracle=None,
    opendss_only_for_full_recheck: bool = False,
    solver_args: argparse.Namespace | None = None,
    safety_economy_tradeoff: float = 0.5,
) -> tuple[LemmingOptimizationRunResult, dict[str, Any] | None]:
    evaluator_args = argparse.Namespace(**vars(solver_args)) if solver_args is not None else argparse.Namespace()
    evaluator_args.prefer_opendss_in_full_recheck = not opendss_only_for_full_recheck
    evaluator = _build_evaluator(args=evaluator_args)

    bridge = OptimizerBridge(
        evaluator=evaluator,
        strategy_ids=opt_case.strategy_candidates,
        search_spaces=opt_case.search_spaces,
    )

    optimizer = LemmingOptimizer(
        bridge=bridge,
        config=LemmingOptimizerConfig(
            population_size=population_size,
            generations=generations,
            elite_count=max(2, population_size // 4),
            mutation_rate=0.35,
            mutation_scale_power=0.15,
            mutation_scale_duration=0.15,
            random_seed=42,
            reinit_fraction=0.20,
            tournament_size=3,
            verbose=True,
        ),
        safety_economy_tradeoff=safety_economy_tradeoff,
    )

    logger.info("=" * 88)
    logger.info("开始场景优化：%s", opt_case.internal_model_id)
    logger.info("候选策略：%s", opt_case.strategy_candidates)
    logger.info("=" * 88)

    optimizer_oracle = None if opendss_only_for_full_recheck else network_oracle
    if network_oracle is not None:
        scope = "仅最终 full_recheck" if optimizer_oracle is None else "fast_proxy 与 full_recheck"
        logger.info("OpenDSS 参与范围：%s；每次小时约束均加载 runtime manifest 中的全部启用负荷。", scope)

    run_result = optimizer.run(ctx=opt_case.context, network_oracle=optimizer_oracle)
    _ensure_best_full_recheck(
        evaluator=evaluator,
        opt_case=opt_case,
        run_result=run_result,
        network_oracle=network_oracle,
    )

    scenario_out_dir = output_root / opt_case.internal_model_id
    export_paths = export_optimization_run(
        output_dir=scenario_out_dir,
        run_result=run_result,
        case_name=opt_case.internal_model_id,
        enable_plots=generate_plots,
    )

    diagnostics = _build_engine_diagnostics(opt_case, run_result, evaluator)
    try:
        scenario_out_dir.mkdir(parents=True, exist_ok=True)
        with open(scenario_out_dir / "engine_diagnostics.json", "w", encoding="utf-8") as f:
            json.dump(diagnostics, f, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:  # pragma: no cover
        logger.warning("写入 engine_diagnostics.json 失败：%s", exc)

    logger.info("场景完成：%s", opt_case.internal_model_id)
    for k, v in export_paths.items():
        logger.info("  %s: %s", k, v)

    if run_result.best_result is not None:
        best = run_result.best_result.summary_dict()
        logger.info(
            "  最优折中解 | strategy=%s | "
            "P=%.2f kW | "
            "E=%.2f kWh | "
            "NPV=%.2f | "
            "Payback=%s | "
            "Mode=%s",
            best['strategy_id'],
            best['rated_power_kw'],
            best['rated_energy_kwh'],
            best.get('npv_yuan', float('nan')),
            best.get('simple_payback_years', float('nan')),
            getattr(run_result.best_result.annual_operation_result, 'evaluation_mode', ''),
        )

    return run_result, _best_summary_row(opt_case, run_result)


def _collect_diagnostics_into_root(output_root: Path) -> None:
    """把每个场景的 engine_diagnostics.json 合并写到 output_root/engine_diagnostics.json。"""
    overall: list[dict[str, Any]] = []
    for path in sorted(output_root.glob("*/engine_diagnostics.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                overall.append(json.load(f))
        except Exception:
            continue
    if not overall:
        return
    payload = {
        "scenarios": overall,
        "scenario_count": len(overall),
    }
    try:
        with open(output_root / "engine_diagnostics.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:  # pragma: no cover
        logger.warning("写入合并 engine_diagnostics.json 失败：%s", exc)


def main() -> None:
    args = parse_args()

    registry_path = Path(args.registry).resolve()
    strategy_library_path = Path(args.strategy_library).resolve()
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    operation_config, safety_config, service_config = build_global_configs(args)
    network_oracle = _build_network_oracle(args)

    logger.info("=" * 88)
    logger.info("工商业配储优化主程序启动")
    logger.info("注册表：%s", registry_path)
    logger.info("策略库：%s", strategy_library_path)
    logger.info("输出目录：%s", output_root)
    logger.info("优化参数：总代数=%d，每代种群=%d", args.generations, args.population_size)
    logger.info(
        "SOC 参数："
        "年度初始SOC=%.3f，"
        "日末模式=%s，"
        "固定日末目标=%.3f，"
        "日末容差=±%.3f",
        _clamp_float(args.initial_soc, 0.50, 0.0, 1.0),
        operation_config.terminal_soc_mode,
        operation_config.fixed_terminal_soc_target,
        operation_config.daily_terminal_soc_tolerance,
    )
    logger.info("OpenDSS oracle：%s", '启用' if network_oracle is not None else '未启用')
    logger.info("安全-经济权衡系数：%.2f（0=纯经济，1=纯安全）", args.safety_economy_tradeoff)
    if network_oracle is not None:
        opendss_scope = "仅最终 full_recheck" if bool(args.opendss_only_for_full_recheck) else "优化阶段 fast_proxy + full_recheck 全流程"
        logger.info("OpenDSS 调用范围：%s", opendss_scope)
    logger.info("=" * 88)

    cases = load_optimization_cases(
        registry_path=registry_path,
        strategy_library_path=strategy_library_path,
        base_dir=registry_path.parent,
        operation_config=operation_config,
        safety_config=safety_config,
        service_config=service_config,
        only_enabled_and_optimizable=True,
    )

    if args.target_id:
        cases = [c for c in cases if c.internal_model_id == args.target_id]

    if not cases:
        raise RuntimeError("没有找到可运行的场景。请检查注册表 enabled / optimize / target-id 设置。")

    logger.info("共加载 %d 个待优化场景。", len(cases))

    overall_rows: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        logger.info("=" * 88)
        logger.info(
            "开始场景优化 [%d/%d]：%s | "
            "总代数=%d | 每代种群=%d",
            idx, len(cases), case.internal_model_id,
            args.generations, args.population_size,
        )
        logger.info("=" * 88)
        _, row = run_one_case(
            opt_case=case,
            output_root=output_root,
            population_size=int(args.population_size),
            generations=int(args.generations),
            generate_plots=not args.disable_plots,
            network_oracle=network_oracle,
            opendss_only_for_full_recheck=bool(args.opendss_only_for_full_recheck),
            solver_args=args,
            safety_economy_tradeoff=args.safety_economy_tradeoff,
        )
        if row is not None:
            overall_rows.append(row)

    if overall_rows:
        overall_path = output_root / "overall_best_schemes.json"
        with open(overall_path, "w", encoding="utf-8") as f:
            json.dump(overall_rows, f, ensure_ascii=False, indent=2)
        logger.info("已导出总体最优方案汇总：%s", overall_path)

    _collect_diagnostics_into_root(output_root)


if __name__ == "__main__":
    main()
