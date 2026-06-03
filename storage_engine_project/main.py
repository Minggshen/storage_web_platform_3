# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

from storage_engine_project.logging_config import get_logger

logger = get_logger(__name__)


def _clamp_progress_percent(value: float) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    return max(0.0, min(100.0, float(value)))


def _log_solver_progress(
    percent: float,
    label: str,
    detail: str,
    phase: str,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "percent": round(_clamp_progress_percent(percent), 2),
        "label": str(label),
        "detail": str(detail),
        "phase": str(phase),
    }
    for key, value in extra.items():
        if value is None:
            continue
        if isinstance(value, float):
            payload[key] = round(value, 6) if math.isfinite(value) else None
        else:
            payload[key] = value
    logger.info("SOLVER_PROGRESS %s", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _span_percent(start: float, end: float, fraction: float) -> float:
    bounded = max(0.0, min(1.0, float(fraction) if math.isfinite(float(fraction)) else 0.0))
    return float(start) + (float(end) - float(start)) * bounded

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
from storage_engine_project.optimization.pareto_utils import dominates, select_best_compromise
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
except ImportError:  # pragma: no cover
    OpenDSSConstraintOracle = None
    OpenDSSOracleConfig = None


def _env_str(name: str, default: str = "") -> str:
    val = os.getenv(name)
    return str(val) if val is not None else default


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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(float(raw))
    except Exception:
        return int(default)


def _clamp_float(value: Any, default: float, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    if not math.isfinite(parsed):
        parsed = float(default)
    return float(min(max(parsed, lower), upper))


DEFAULT_ECONOMIC_METRIC_WEIGHTS = {
    "npv": 0.45,
    "irr": 0.20,
    "payback": 0.25,
    "investment": 0.10,
}
DEFAULT_SAFETY_METRIC_WEIGHTS = {
    "transformer": 0.25,
    "voltage": 0.25,
    "line": 0.25,
    "cycle": 0.25,
}


def _weight_dict(args: argparse.Namespace, names: dict[str, str], defaults: dict[str, float]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for key, attr in names.items():
        weights[key] = max(0.0, _clamp_float(getattr(args, attr, defaults[key]), defaults[key], 0.0, 1.0))
    total = sum(weights.values())
    if total <= 1e-12:
        return dict(defaults)
    return {key: value / total for key, value in weights.items()}


def _economic_metric_weights(args: argparse.Namespace) -> dict[str, float]:
    return _weight_dict(
        args,
        {
            "npv": "economic_weight_npv",
            "irr": "economic_weight_irr",
            "payback": "economic_weight_payback",
            "investment": "economic_weight_investment",
        },
        DEFAULT_ECONOMIC_METRIC_WEIGHTS,
    )


def _safety_metric_weights(args: argparse.Namespace) -> dict[str, float]:
    return _weight_dict(
        args,
        {
            "transformer": "safety_weight_transformer",
            "voltage": "safety_weight_voltage",
            "line": "safety_weight_line",
            "cycle": "safety_weight_cycle",
        },
        DEFAULT_SAFETY_METRIC_WEIGHTS,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="工商业配储年度优化整合版主程序")
    parser.add_argument("--registry", type=str, default="inputs/registry/node_registry.xlsx", help="场景注册表路径")
    parser.add_argument("--strategy-library", type=str, default="inputs/storage/工商业储能设备策略库.xlsx", help="储能设备策略库路径")
    parser.add_argument("--target-id", type=str, default="", help="仅运行指定 internal_model_id；为空则跑所有启用场景")
    parser.add_argument("--output-dir", type=str, default="outputs/integrated_optimization", help="结果输出目录")
    parser.add_argument("--population-size", type=int, default=16, help="种群规模")
    parser.add_argument("--generations", type=int, default=8, help="优化代数")
    parser.add_argument("--solver-tier", type=str, default="",
                        choices=["fast", "standard", "delivery", ""],
                        help="求解器预设档位：fast=快速预览(8×3,GA轻量代理,Top-3 OpenDSS重校核), standard=标准求解(12×5,GA轻量代理,Top-3 OpenDSS重校核), delivery=交付求解(16×8,GA全流程OpenDSS)")
    parser.add_argument("--disable-plots", action="store_true", help="不生成绘图文件")
    parser.add_argument("--safety-economy-tradeoff", type=float, default=0.5, help="安全-经济权衡系数：0=纯经济最优，1=纯安全最优（默认 0.5 并重）")
    parser.add_argument("--economic-weight-npv", type=float, default=DEFAULT_ECONOMIC_METRIC_WEIGHTS["npv"], help="经济性子指标权重：NPV")
    parser.add_argument("--economic-weight-irr", type=float, default=DEFAULT_ECONOMIC_METRIC_WEIGHTS["irr"], help="经济性子指标权重：IRR")
    parser.add_argument("--economic-weight-payback", type=float, default=DEFAULT_ECONOMIC_METRIC_WEIGHTS["payback"], help="经济性子指标权重：回收期")
    parser.add_argument("--economic-weight-investment", type=float, default=DEFAULT_ECONOMIC_METRIC_WEIGHTS["investment"], help="经济性子指标权重：初始投资")
    parser.add_argument("--safety-weight-transformer", type=float, default=DEFAULT_SAFETY_METRIC_WEIGHTS["transformer"], help="安全性子指标权重：变压器越限")
    parser.add_argument("--safety-weight-voltage", type=float, default=DEFAULT_SAFETY_METRIC_WEIGHTS["voltage"], help="安全性子指标权重：电压越限")
    parser.add_argument("--safety-weight-line", type=float, default=DEFAULT_SAFETY_METRIC_WEIGHTS["line"], help="安全性子指标权重：线路过载")
    parser.add_argument("--safety-weight-cycle", type=float, default=DEFAULT_SAFETY_METRIC_WEIGHTS["cycle"], help="安全性子指标权重：设备策略约束（年循环上限/时长边界）")
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
    parser.add_argument("--opendss-engine-recycle-solve-interval", type=int, default=_env_int("STORAGE_OPENDSS_ENGINE_RECYCLE_SOLVE_INTERVAL", 480), help="OpenDSS COM 引擎按 Solve 次数主动重建；<=0 表示禁用")
    parser.add_argument("--opendss-engine-recycle-compile-interval", type=int, default=_env_int("STORAGE_OPENDSS_ENGINE_RECYCLE_COMPILE_INTERVAL", 240), help="OpenDSS COM 引擎按 Compile 次数主动重建；<=0 表示禁用")
    parser.add_argument("--opendss-engine-error-retry-count", type=int, default=_env_int("STORAGE_OPENDSS_ENGINE_ERROR_RETRY_COUNT", 1), help="OpenDSS 482/OOM 等后端错误发生时，重建引擎后重试当前小时的次数")
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
        engine_recycle_solve_interval=int(args.opendss_engine_recycle_solve_interval),
        engine_recycle_compile_interval=int(args.opendss_engine_recycle_compile_interval),
        engine_error_retry_count=int(args.opendss_engine_error_retry_count),
        compile_each_call=False,  # oracle 内部按日控制编译，此参数不再生效
        allow_engine_fallback=False,
        log_failures=True,
    )
    try:
        oracle = OpenDSSConstraintOracle(config=cfg)
        logger.info("已启用 OpenDSS oracle，Master=%s", args.dss_master_path)
        logger.info(
            "OpenDSS 引擎回收：Solve间隔=%d，Compile间隔=%d，错误重试=%d",
            cfg.engine_recycle_solve_interval,
            cfg.engine_recycle_compile_interval,
            cfg.engine_error_retry_count,
        )
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
            preferred_solvers=("OSQP", "ECOS", "SCS"),
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
            full_recheck_max_payback_years=10.0,
            full_recheck_min_npv_to_investment_ratio=0.0,
            full_recheck_require_non_negative_cashflow=True,
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
    progress_callback=None,
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
            if progress_callback is not None:
                progress_callback({
                    "event": "final_recheck_already_valid",
                    "strategy_id": best.decision.strategy_id,
                    "rated_power_kw": float(best.decision.rated_power_kw),
                    "duration_h": float(best.decision.duration_h()),
                })
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
            if progress_callback is not None:
                progress_callback({
                    "event": "final_recheck_already_valid",
                    "strategy_id": best.decision.strategy_id,
                    "rated_power_kw": float(best.decision.rated_power_kw),
                    "duration_h": float(best.decision.duration_h()),
                })
            return
        logger.info("调用 OpenDSS oracle 对最终折中解执行全年重校核...")

    if progress_callback is not None:
        progress_callback({
            "event": "final_recheck_start",
            "strategy_id": best.decision.strategy_id,
            "rated_power_kw": float(best.decision.rated_power_kw),
            "duration_h": float(best.decision.duration_h()),
        })
    rechecked = evaluator.evaluate_decision(
        ctx=opt_case.context,
        decision=best.decision,
        network_oracle=network_oracle,
        force_full_recheck=True,
    )
    if progress_callback is not None:
        progress_callback({
            "event": "final_recheck_complete",
            "strategy_id": best.decision.strategy_id,
            "rated_power_kw": float(best.decision.rated_power_kw),
            "duration_h": float(best.decision.duration_h()),
        })
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


def _pareto_rank(results: list[FitnessEvaluationResult]) -> list[int]:
    """Compute Pareto rank for each result (0 = non-dominated, higher = more dominated)."""
    n = len(results)
    ranks = [0] * n
    for i in range(n):
        for j in range(n):
            if i != j and dominates(results[j], results[i]):
                ranks[i] += 1
    return ranks


def _is_valid_full_recheck_result(
    result: FitnessEvaluationResult,
    network_oracle: object | None,
) -> bool:
    """Check that a result has full_recheck mode AND, if Oracle is active, exportable OpenDSS data."""
    meta = getattr(result, "metadata", {}) or {}
    ann = getattr(result, "annual_operation_result", None)
    if not (bool(meta.get("recheck_performed", False))
            and ann is not None
            and getattr(ann, "evaluation_mode", "") == "full_recheck"):
        return False
    if network_oracle is not None:
        trace_stats = _opendss_trace_stats(ann)
        return _has_opendss_export_values(trace_stats)
    return True


def _ensure_topk_full_recheck(
    evaluator: StorageFitnessEvaluator,
    opt_case: Any,
    run_result: LemmingOptimizationRunResult,
    network_oracle=None,
    k: int = 3,
    safety_economy_tradeoff: float = 0.5,
    economic_metric_weights: dict[str, float] | None = None,
    safety_metric_weights: dict[str, float] | None = None,
    progress_callback=None,
) -> None:
    """GA 结束后对 archive 中 Top-K Pareto 候选执行 OpenDSS 全年重校核并重排。"""
    archive = list(run_result.archive_results)
    if not archive:
        return

    pareto_ranks = _pareto_rank(archive)
    sorted_indices = sorted(range(len(archive)), key=lambda i: pareto_ranks[i])
    top_k_indices = sorted_indices[: min(k, len(sorted_indices))]

    logger.info("对 Top-%d 候选方案执行 OpenDSS 全年重校核...", len(top_k_indices))
    if progress_callback is not None:
        progress_callback({
            "event": "topk_recheck_start",
            "candidate_total": len(top_k_indices),
        })
    for order, idx in enumerate(top_k_indices, start=1):
        candidate = archive[idx]
        meta = getattr(candidate, "metadata", {}) or {}
        ann = getattr(candidate, "annual_operation_result", None)
        rechecked = (
            bool(meta.get("recheck_performed", False))
            and ann is not None
            and getattr(ann, "evaluation_mode", "") == "full_recheck"
        )
        trace_stats = _opendss_trace_stats(ann)
        if rechecked and _has_opendss_export_values(trace_stats):
            logger.info(
                "  候选 #%d 已有 OpenDSS 重校核数据，跳过（P=%.1fkW E=%.1fkWh）。",
                idx + 1, candidate.decision.rated_power_kw, candidate.decision.rated_energy_kwh,
            )
            if progress_callback is not None:
                progress_callback({
                    "event": "topk_recheck_skip",
                    "candidate_index": order,
                    "candidate_total": len(top_k_indices),
                    "archive_index": idx + 1,
                    "strategy_id": candidate.decision.strategy_id,
                    "rated_power_kw": float(candidate.decision.rated_power_kw),
                    "duration_h": float(candidate.decision.duration_h()),
                })
            continue

        logger.info(
            "  重校核候选 #%d: %s P=%.1fkW E=%.1fkWh",
            idx + 1, candidate.decision.strategy_id,
            candidate.decision.rated_power_kw, candidate.decision.rated_energy_kwh,
        )
        if progress_callback is not None:
            progress_callback({
                "event": "topk_recheck_candidate_start",
                "candidate_index": order,
                "candidate_total": len(top_k_indices),
                "archive_index": idx + 1,
                "strategy_id": candidate.decision.strategy_id,
                "rated_power_kw": float(candidate.decision.rated_power_kw),
                "duration_h": float(candidate.decision.duration_h()),
            })
        rechecked_result = evaluator.evaluate_decision(
            ctx=opt_case.context,
            decision=candidate.decision,
            network_oracle=network_oracle,
            force_full_recheck=True,
        )
        run_result.archive_results = _replace_same_decision(run_result.archive_results, rechecked_result)
        run_result.population_results = _replace_same_decision(run_result.population_results, rechecked_result)
        if progress_callback is not None:
            progress_callback({
                "event": "topk_recheck_candidate_complete",
                "candidate_index": order,
                "candidate_total": len(top_k_indices),
                "archive_index": idx + 1,
                "strategy_id": candidate.decision.strategy_id,
                "rated_power_kw": float(candidate.decision.rated_power_kw),
                "duration_h": float(candidate.decision.duration_h()),
            })

    # 闭环保证：最终 best 必须通过 _is_valid_full_recheck_result 校验。
    # 每轮补做至多一个候选，archive 有限，上界为 archive 规模 + 1。
    max_rounds = len(run_result.archive_results) + 1
    for _round in range(max_rounds):
        run_result.best_result = select_best_compromise(
            run_result.archive_results,
            safety_economy_tradeoff=safety_economy_tradeoff,
            economic_metric_weights=economic_metric_weights,
            safety_metric_weights=safety_metric_weights,
        )
        best = run_result.best_result
        if best is None:
            break
        if _is_valid_full_recheck_result(best, network_oracle):
            break

        logger.info(
            "  补做 OpenDSS 全年校核: %s P=%.1fkW E=%.1fkWh (第%d轮)",
            best.decision.strategy_id, best.decision.rated_power_kw, best.decision.rated_energy_kwh, _round + 1,
        )
        if progress_callback is not None:
            progress_callback({
                "event": "closure_recheck_start",
                "round": _round + 1,
                "max_rounds": max_rounds,
                "strategy_id": best.decision.strategy_id,
                "rated_power_kw": float(best.decision.rated_power_kw),
                "duration_h": float(best.decision.duration_h()),
            })
        rechecked = evaluator.evaluate_decision(
            ctx=opt_case.context,
            decision=best.decision,
            network_oracle=network_oracle,
            force_full_recheck=True,
        )
        run_result.archive_results = _replace_same_decision(run_result.archive_results, rechecked)
        run_result.population_results = _replace_same_decision(run_result.population_results, rechecked)
        if progress_callback is not None:
            progress_callback({
                "event": "closure_recheck_complete",
                "round": _round + 1,
                "max_rounds": max_rounds,
                "strategy_id": best.decision.strategy_id,
                "rated_power_kw": float(best.decision.rated_power_kw),
                "duration_h": float(best.decision.duration_h()),
            })
    else:
        raise RuntimeError(
            f"重校核闭环未在 {max_rounds} 轮内收敛：archive 共 "
            f"{len(run_result.archive_results)} 个候选，最终 best 仍未通过 OpenDSS 校核校验。"
        )

    logger.info("Top-%d 重校核完成，已更新最优折中解。", len(top_k_indices))
    if progress_callback is not None:
        progress_callback({
            "event": "topk_recheck_complete",
            "candidate_total": len(top_k_indices),
        })


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
                "generation_wall_time_s",
                "evaluator_eval_count",
            ) if k in rec})

    timing_stats: dict[str, Any] = {}
    try:
        timing_stats = evaluator.get_timing_stats()
    except Exception:
        pass

    opendss_trace_stats: dict[str, Any] = {}
    best_result = run_result.best_result
    if best_result is not None:
        ann = getattr(best_result, "annual_operation_result", None)
        if ann is not None:
            try:
                opendss_trace_stats = _opendss_trace_stats(ann)
            except Exception:
                pass

    best_edit_fallback_count = 0
    if best_result is not None:
        ann = getattr(best_result, "annual_operation_result", None)
        if ann is not None:
            for exec_result in getattr(ann, "daily_exec_objects", None) or []:
                for trace in getattr(exec_result, "network_trace", None) or []:
                    if isinstance(trace, dict):
                        fb = int(trace.get("edit_fallback_count", 0))
                        best_edit_fallback_count = max(best_edit_fallback_count, fb)

    return {
        "scenario": getattr(opt_case, "internal_model_id", None),
        "cache_stats": cache_stats,
        "constraint_breakdown": constraint_breakdown,
        "population_history": population_history,
        "timing_stats": timing_stats,
        "opendss_trace_stats": opendss_trace_stats,
        "best_edit_fallback_count": best_edit_fallback_count,
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
    progress_start_percent: float = 8.0,
    progress_end_percent: float = 96.0,
    case_index: int = 1,
    case_total: int = 1,
) -> tuple[LemmingOptimizationRunResult, dict[str, Any] | None]:
    case_width = max(0.0, float(progress_end_percent) - float(progress_start_percent))

    def _case_percent(relative: float) -> float:
        return float(progress_start_percent) + case_width * max(0.0, min(1.0, float(relative)))

    def _int_value(value: Any, default: int = 0) -> int:
        try:
            return int(float(value))
        except Exception:
            return int(default)

    case_prefix = f"第 {case_index}/{case_total} 个场景"
    ga_start_rel = 0.04
    if opendss_only_for_full_recheck:
        ga_end_rel = 0.40
        recheck_start_rel = 0.40
    else:
        ga_end_rel = 0.86
        recheck_start_rel = 0.86
    recheck_end_rel = 0.93
    export_start_rel = 0.93

    _log_solver_progress(
        _case_percent(0.01),
        "准备场景求解",
        f"{case_prefix}，正在构建调度器、评估器和候选搜索空间。",
        "case_prepare",
        case_index=case_index,
        case_total=case_total,
        scenario_id=opt_case.internal_model_id,
    )

    evaluator_args = argparse.Namespace(**vars(solver_args)) if solver_args is not None else argparse.Namespace()
    evaluator_args.prefer_opendss_in_full_recheck = not opendss_only_for_full_recheck
    economic_metric_weights = _economic_metric_weights(evaluator_args)
    safety_metric_weights = _safety_metric_weights(evaluator_args)
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
        economic_metric_weights=economic_metric_weights,
        safety_metric_weights=safety_metric_weights,
    )

    _case_t0 = time.perf_counter()

    logger.info("=" * 88)
    logger.info("开始场景优化：%s", opt_case.internal_model_id)
    logger.info("候选策略：%s", opt_case.strategy_candidates)
    logger.info("=" * 88)

    optimizer_oracle = None if opendss_only_for_full_recheck else network_oracle
    if network_oracle is not None:
        scope = "仅最终 Top-K full_recheck" if optimizer_oracle is None else "fast_proxy 与 full_recheck"
        logger.info("OpenDSS 参与范围：%s；每次小时约束均加载 runtime manifest 中的全部启用负荷。", scope)

    # 当 GA 搜索阶段不跑 OpenDSS 时，禁用逐候选 full_recheck
    if opendss_only_for_full_recheck:
        evaluator.config.full_recheck_for_fast_feasible_only = False

    def _emit_ga_progress(event: dict[str, Any]) -> None:
        event_name = str(event.get("event") or "")
        gen = max(1, _int_value(event.get("generation"), 1))
        gen_total = max(1, _int_value(event.get("generations"), generations))
        pop_total = max(1, _int_value(event.get("population_size"), population_size))
        candidate_idx = max(1, min(pop_total, _int_value(event.get("candidate_index"), 1)))
        gen_span = ga_end_rel - ga_start_rel

        if event_name == "ga_generation_start":
            fraction = (gen - 1) / gen_total
            _log_solver_progress(
                _case_percent(ga_start_rel + gen_span * fraction),
                "GA 候选搜索",
                f"{case_prefix}，开始第 {gen}/{gen_total} 代候选评估。",
                "ga_generation",
                case_index=case_index,
                case_total=case_total,
                generation=gen,
                generations=gen_total,
                population_size=pop_total,
            )
            return

        if event_name in {"ga_candidate_start", "ga_candidate_complete", "ga_candidate_cache_hit"}:
            start_fraction = ((gen - 1) + (candidate_idx - 1) / pop_total) / gen_total
            end_fraction = ((gen - 1) + candidate_idx / pop_total) / gen_total
            span_start = _case_percent(ga_start_rel + gen_span * start_fraction)
            span_end = _case_percent(ga_start_rel + gen_span * end_fraction)
            strategy_id = str(event.get("strategy_id") or "")
            power_kw = event.get("rated_power_kw")
            duration_h = event.get("duration_h")
            suffix = ""
            if power_kw is not None and duration_h is not None:
                suffix = f"，{strategy_id} P={float(power_kw):.0f}kW 时长={float(duration_h):.2f}h"

            if event_name == "ga_candidate_start":
                _log_solver_progress(
                    span_start,
                    "GA 候选评估",
                    f"{case_prefix}，第 {gen}/{gen_total} 代，候选 {candidate_idx}/{pop_total}{suffix}。",
                    "ga_candidate",
                    case_index=case_index,
                    case_total=case_total,
                    generation=gen,
                    generations=gen_total,
                    candidate_index=candidate_idx,
                    candidate_total=pop_total,
                    span_start_percent=span_start,
                    span_end_percent=span_end,
                )
            elif event_name == "ga_candidate_cache_hit":
                _log_solver_progress(
                    span_end,
                    "GA 候选复用",
                    f"{case_prefix}，第 {gen}/{gen_total} 代，候选 {candidate_idx}/{pop_total} 已复用缓存结果。",
                    "ga_candidate_cache_hit",
                    case_index=case_index,
                    case_total=case_total,
                    generation=gen,
                    generations=gen_total,
                    candidate_index=candidate_idx,
                    candidate_total=pop_total,
                )
            else:
                _log_solver_progress(
                    span_end,
                    "GA 候选评估",
                    f"{case_prefix}，第 {gen}/{gen_total} 代，候选 {candidate_idx}/{pop_total} 已完成。",
                    "ga_candidate",
                    case_index=case_index,
                    case_total=case_total,
                    generation=gen,
                    generations=gen_total,
                    candidate_index=candidate_idx,
                    candidate_total=pop_total,
                )
            return

        if event_name == "ga_generation_complete":
            fraction = gen / gen_total
            _log_solver_progress(
                _case_percent(ga_start_rel + gen_span * fraction),
                "GA 迭代完成",
                f"{case_prefix}，第 {gen}/{gen_total} 代完成，进入下一代或重校核准备。",
                "ga_generation",
                case_index=case_index,
                case_total=case_total,
                generation=gen,
                generations=gen_total,
                population_size=pop_total,
                unique_evaluation_count=_int_value(event.get("unique_evaluation_count"), 0),
            )

    def _emit_recheck_progress(event: dict[str, Any]) -> None:
        event_name = str(event.get("event") or "")
        recheck_span = recheck_end_rel - recheck_start_rel
        topk_end_rel = recheck_start_rel + recheck_span * 0.85
        closure_start_rel = topk_end_rel

        if event_name == "topk_recheck_start":
            total = max(1, _int_value(event.get("candidate_total"), 1))
            _log_solver_progress(
                _case_percent(recheck_start_rel),
                "OpenDSS 全年重校核",
                f"{case_prefix}，GA 已完成，开始 Top-{total} 候选全年潮流重校核。",
                "topk_recheck",
                case_index=case_index,
                case_total=case_total,
                candidate_total=total,
            )
            return

        if event_name in {"topk_recheck_candidate_start", "topk_recheck_candidate_complete", "topk_recheck_skip"}:
            total = max(1, _int_value(event.get("candidate_total"), 1))
            idx = max(1, min(total, _int_value(event.get("candidate_index"), 1)))
            span_start = _case_percent(_span_percent(recheck_start_rel, topk_end_rel, (idx - 1) / total))
            span_end = _case_percent(_span_percent(recheck_start_rel, topk_end_rel, idx / total))
            archive_index = _int_value(event.get("archive_index"), idx)
            if event_name == "topk_recheck_candidate_start":
                _log_solver_progress(
                    span_start,
                    "OpenDSS 全年重校核",
                    f"{case_prefix}，正在重校核 Top-{idx}/{total} 候选（Archive #{archive_index}）。",
                    "topk_recheck_candidate",
                    case_index=case_index,
                    case_total=case_total,
                    candidate_index=idx,
                    candidate_total=total,
                    span_start_percent=span_start,
                    span_end_percent=span_end,
                )
            elif event_name == "topk_recheck_skip":
                _log_solver_progress(
                    span_end,
                    "OpenDSS 重校核复用",
                    f"{case_prefix}，Top-{idx}/{total} 候选已有有效全年重校核结果，已跳过。",
                    "topk_recheck_candidate",
                    case_index=case_index,
                    case_total=case_total,
                    candidate_index=idx,
                    candidate_total=total,
                )
            else:
                _log_solver_progress(
                    span_end,
                    "OpenDSS 全年重校核",
                    f"{case_prefix}，Top-{idx}/{total} 候选全年重校核完成。",
                    "topk_recheck_candidate",
                    case_index=case_index,
                    case_total=case_total,
                    candidate_index=idx,
                    candidate_total=total,
                )
            return

        if event_name in {"closure_recheck_start", "closure_recheck_complete"}:
            max_rounds = max(1, _int_value(event.get("max_rounds"), 1))
            round_index = max(1, min(max_rounds, _int_value(event.get("round"), 1)))
            span_start = _case_percent(_span_percent(closure_start_rel, recheck_end_rel, (round_index - 1) / max_rounds))
            span_end = _case_percent(_span_percent(closure_start_rel, recheck_end_rel, round_index / max_rounds))
            if event_name == "closure_recheck_start":
                _log_solver_progress(
                    span_start,
                    "补做最终校核",
                    f"{case_prefix}，最终折中解尚未满足全年重校核要求，补做第 {round_index} 轮。",
                    "closure_recheck",
                    case_index=case_index,
                    case_total=case_total,
                    round=round_index,
                    max_rounds=max_rounds,
                    span_start_percent=span_start,
                    span_end_percent=span_end,
                )
            else:
                _log_solver_progress(
                    span_end,
                    "补做最终校核",
                    f"{case_prefix}，第 {round_index} 轮补做全年重校核完成。",
                    "closure_recheck",
                    case_index=case_index,
                    case_total=case_total,
                    round=round_index,
                    max_rounds=max_rounds,
                )
            return

        if event_name == "topk_recheck_complete":
            _log_solver_progress(
                _case_percent(recheck_end_rel),
                "OpenDSS 重校核完成",
                f"{case_prefix}，Top-K 重校核与最终折中解校验已完成。",
                "topk_recheck",
                case_index=case_index,
                case_total=case_total,
            )
            return

        if event_name in {"final_recheck_start", "final_recheck_complete", "final_recheck_already_valid"}:
            span_start = _case_percent(recheck_start_rel)
            span_end = _case_percent(recheck_end_rel)
            if event_name == "final_recheck_start":
                _log_solver_progress(
                    span_start,
                    "最终方案全年重校核",
                    f"{case_prefix}，正在对最终折中解执行全年 OpenDSS 校核。",
                    "final_recheck",
                    case_index=case_index,
                    case_total=case_total,
                    span_start_percent=span_start,
                    span_end_percent=span_end,
                )
            elif event_name == "final_recheck_already_valid":
                _log_solver_progress(
                    span_end,
                    "最终方案已校核",
                    f"{case_prefix}，最终折中解已包含有效全年 OpenDSS 校核结果。",
                    "final_recheck",
                    case_index=case_index,
                    case_total=case_total,
                )
            else:
                _log_solver_progress(
                    span_end,
                    "最终方案全年重校核",
                    f"{case_prefix}，最终折中解全年 OpenDSS 校核完成。",
                    "final_recheck",
                    case_index=case_index,
                    case_total=case_total,
                )

    run_result = optimizer.run(
        ctx=opt_case.context,
        network_oracle=optimizer_oracle,
        progress_callback=_emit_ga_progress,
    )

    if opendss_only_for_full_recheck:
        _ensure_topk_full_recheck(
            evaluator=evaluator,
            opt_case=opt_case,
            run_result=run_result,
            network_oracle=network_oracle,
            k=3,
            safety_economy_tradeoff=safety_economy_tradeoff,
            economic_metric_weights=economic_metric_weights,
            safety_metric_weights=safety_metric_weights,
            progress_callback=_emit_recheck_progress,
        )
    else:
        _ensure_best_full_recheck(
            evaluator=evaluator,
            opt_case=opt_case,
            run_result=run_result,
            network_oracle=network_oracle,
            progress_callback=_emit_recheck_progress,
        )

    scenario_out_dir = output_root / opt_case.internal_model_id
    _log_solver_progress(
        _case_percent(export_start_rel),
        "正在导出结果",
        f"{case_prefix}，正在写入 CSV、JSON、图表和诊断文件。",
        "export",
        case_index=case_index,
        case_total=case_total,
        scenario_id=opt_case.internal_model_id,
    )
    export_paths = export_optimization_run(
        output_dir=scenario_out_dir,
        run_result=run_result,
        case_name=opt_case.internal_model_id,
        enable_plots=generate_plots,
        timing_stats=evaluator.get_timing_stats(),
        safety_economy_tradeoff=safety_economy_tradeoff,
        economic_metric_weights=economic_metric_weights,
        safety_metric_weights=safety_metric_weights,
    )

    diagnostics = _build_engine_diagnostics(opt_case, run_result, evaluator)
    diagnostics["total_wall_time_s"] = time.perf_counter() - _case_t0
    try:
        scenario_out_dir.mkdir(parents=True, exist_ok=True)
        with open(scenario_out_dir / "engine_diagnostics.json", "w", encoding="utf-8") as f:
            json.dump(diagnostics, f, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:  # pragma: no cover
        logger.warning("写入 engine_diagnostics.json 失败：%s", exc)
    _log_solver_progress(
        _case_percent(0.99),
        "场景结果已导出",
        f"{case_prefix}，结果文件与引擎诊断已写入。",
        "export",
        case_index=case_index,
        case_total=case_total,
        scenario_id=opt_case.internal_model_id,
    )

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

    _log_solver_progress(1, "求解器进程已启动", "正在读取运行参数并准备输出目录。", "startup")

    registry_path = Path(args.registry).resolve()
    strategy_library_path = Path(args.strategy_library).resolve()
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    operation_config, safety_config, service_config = build_global_configs(args)
    _log_solver_progress(3, "初始化网络校核", "正在初始化运行配置与 OpenDSS oracle。", "startup")
    network_oracle = _build_network_oracle(args)

    logger.info("=" * 88)
    logger.info("工商业配储优化主程序启动")
    logger.info("注册表：%s", registry_path)
    logger.info("策略库：%s", strategy_library_path)
    logger.info("输出目录：%s", output_root)

    # 求解器档位解析：显式设置 tier 时覆盖 population/generations/opendss/plots
    tier = str(getattr(args, "solver_tier", "") or "").strip().lower()
    tier_explicit = bool(tier)
    if tier == "fast":
        effective_pop, effective_gen = 8, 3
        effective_opendss_only = True
        effective_disable_plots = True
    elif tier == "delivery":
        effective_pop, effective_gen = 16, 8
        effective_opendss_only = False
        effective_disable_plots = bool(args.disable_plots)
    else:
        if tier_explicit:
            tier = "standard"
        effective_pop, effective_gen = 12, 5
        effective_opendss_only = True
        effective_disable_plots = bool(args.disable_plots)

    if tier_explicit:
        logger.info(
            "求解器档位：%s (pop=%d, gen=%d, OpenDSS=%s, plots=%s)",
            tier, effective_pop, effective_gen,
            "仅Top-K重校核" if effective_opendss_only else "全流程",
            "否" if effective_disable_plots else "是",
        )
    else:
        effective_pop = int(args.population_size)
        effective_gen = int(args.generations)
        effective_opendss_only = bool(args.opendss_only_for_full_recheck)
        effective_disable_plots = bool(args.disable_plots)

    logger.info("优化参数：总代数=%d，每代种群=%d", effective_gen, effective_pop)
    economic_metric_weights = _economic_metric_weights(args)
    safety_metric_weights = _safety_metric_weights(args)
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
    logger.info("经济性子权重：%s", economic_metric_weights)
    logger.info("安全性子权重：%s", safety_metric_weights)
    if network_oracle is not None:
        opendss_scope = "仅最终 Top-K full_recheck" if effective_opendss_only else "优化阶段 fast_proxy + full_recheck 全流程"
        logger.info("OpenDSS 调用范围：%s", opendss_scope)
    logger.info("=" * 88)

    _log_solver_progress(6, "加载优化场景", "正在读取注册表、策略库、负荷矩阵和电价输入。", "load_cases")
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
    _log_solver_progress(
        8,
        "优化场景已加载",
        f"共加载 {len(cases)} 个待优化场景，开始进入候选搜索。",
        "load_cases",
        case_total=len(cases),
    )

    overall_rows: list[dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        case_start = _span_percent(8.0, 96.0, (idx - 1) / len(cases))
        case_end = _span_percent(8.0, 96.0, idx / len(cases))
        logger.info("=" * 88)
        logger.info(
            "开始场景优化 [%d/%d]：%s | "
            "总代数=%d | 每代种群=%d",
            idx, len(cases), case.internal_model_id,
            effective_gen, effective_pop,
        )
        logger.info("=" * 88)
        _, row = run_one_case(
            opt_case=case,
            output_root=output_root,
            population_size=effective_pop,
            generations=effective_gen,
            generate_plots=not effective_disable_plots,
            network_oracle=network_oracle,
            opendss_only_for_full_recheck=effective_opendss_only,
            solver_args=args,
            safety_economy_tradeoff=args.safety_economy_tradeoff,
            progress_start_percent=case_start,
            progress_end_percent=case_end,
            case_index=idx,
            case_total=len(cases),
        )
        if row is not None:
            overall_rows.append(row)

        # 检查 OpenDSS Edit fallback 次数
        diag_path = output_root / case.internal_model_id / "engine_diagnostics.json"
        try:
            if diag_path.exists():
                with open(diag_path, "r", encoding="utf-8") as f:
                    diag = json.load(f)
                fb = int(diag.get("best_edit_fallback_count", 0))
                if fb > 10:
                    logger.warning(
                        "场景 %s: OpenDSS Edit 回退次数较高（%d），建议检查 Master.dss 或负荷数据稳定性。",
                        case.internal_model_id, fb,
                    )
        except Exception:
            pass

    if overall_rows:
        _log_solver_progress(
            97,
            "汇总最优方案",
            "所有场景已完成，正在写入总体最优方案汇总。",
            "overall_export",
            case_total=len(cases),
        )
        overall_path = output_root / "overall_best_schemes.json"
        with open(overall_path, "w", encoding="utf-8") as f:
            json.dump(overall_rows, f, ensure_ascii=False, indent=2)
        logger.info("已导出总体最优方案汇总：%s", overall_path)

    _collect_diagnostics_into_root(output_root)
    _log_solver_progress(100, "求解流程完成", "总体汇总和诊断文件已完成。", "completed")


if __name__ == "__main__":
    main()
