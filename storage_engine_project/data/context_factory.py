
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from storage_engine_project.config.operation_config import OperationConfig, get_default_operation_config
from storage_engine_project.config.safety_config import SafetyConfig, get_default_safety_config
from storage_engine_project.config.service_config import ServiceConfig, get_default_service_config
from storage_engine_project.data.annual_context_builder import AnnualOperationContext, build_annual_operation_context
from storage_engine_project.data.storage_strategy_loader import load_storage_strategies
from storage_engine_project.optimization.configuration_boundary import compute_storage_configuration_boundary
from storage_engine_project.optimization.optimizer_bridge import SearchSpaceConfig


@dataclass(slots=True)
class RegistryScenario:
    internal_model_id: str
    enabled: bool
    optimize: bool

    node_id: int
    scenario_name: str
    category: str

    node_dir: str
    year_model_map_file: str
    model_library_file: str

    tariff_path: str
    service_calendar_path: str | None

    pv_capacity_kw: float
    q_to_p_ratio: float

    transformer_capacity_kva: float | None
    transformer_pf_limit: float
    transformer_reserve_ratio: float
    grid_interconnection_limit_kw: float | None

    device_power_max_kw: float | None
    search_power_min_kw: float | None
    search_duration_min_h: float | None
    search_duration_max_h: float | None

    include_aux_service_revenue: bool
    include_capacity_revenue: bool
    include_loss_reduction_revenue: bool
    include_degradation_cost: bool
    include_government_subsidy: bool
    include_replacement_cost: bool

    dispatch_mode: str
    daily_demand_shadow_yuan_per_kw: float
    voltage_penalty_coeff_yuan: float
    run_mode: str
    model_year: int

    strategy_candidates: list[str]
    base_strategy_id: str

    extra_meta: dict[str, Any]


def _find_header_row(df_raw: pd.DataFrame) -> int:
    for idx in range(min(20, len(df_raw))):
        row_vals = [str(x).strip() if x is not None else "" for x in df_raw.iloc[idx].tolist()]
        if {"enabled", "optimize_storage", "node_id", "scenario_name", "node_dir"} <= set(row_vals):
            return idx
    raise ValueError("未找到注册表表头行。应至少包含 enabled / optimize_storage / node_id / scenario_name / node_dir。")


def _read_registry(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"注册表不存在：{path}")

    if path.suffix.lower() in {".xlsx", ".xls"}:
        raw = pd.read_excel(path, header=None)
    elif path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, header=None)
    else:
        raise ValueError(f"暂不支持的注册表文件类型：{path.suffix}")

    header_row = _find_header_row(raw)
    headers = [str(x).strip() if x is not None else "" for x in raw.iloc[header_row].tolist()]
    df = raw.iloc[header_row + 1 :].copy()
    df.columns = headers
    df = df.reset_index(drop=True)
    df = df.loc[~df.apply(lambda s: s.isna().all(), axis=1)].reset_index(drop=True)
    return df


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "是", "启用", "参与", "on"}:
        return True
    if text in {"0", "false", "no", "n", "否", "不启用", "不参与", "off"}:
        return False
    return default


def _to_float_or_none(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except Exception:
        return None


def _to_float(value: Any, default: float) -> float:
    v = _to_float_or_none(value)
    return float(default if v is None else v)


def _to_int(value: Any, default: int) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def _resolve_path_like(value: str | None, base_dir: Path) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    p = Path(text)
    if p.is_absolute():
        return str(p.resolve())
    return str((base_dir / p).resolve())


def _build_internal_model_id(row: pd.Series) -> str:
    explicit_id = str(row.get("internal_model_id", "")).strip()
    if explicit_id:
        return explicit_id
    scenario_name = str(row.get("scenario_name", "")).strip()
    if scenario_name:
        return scenario_name
    node_id = _to_int(row.get("node_id", 0), 0)
    return f"node{node_id:02d}" if node_id > 0 else ""


def _resolve_tariff_path(row: pd.Series, base_dir: Path) -> str:
    from_row = _resolve_path_like(row.get("tariff_path", None), base_dir)
    if from_row:
        return from_row
    default_path = _resolve_path_like("inputs/tariff/tariff_annual.xlsx", base_dir)
    return default_path or ""


def load_registry_scenarios(
    registry_path: str | Path,
    base_dir: str | Path = ".",
) -> list[RegistryScenario]:
    df = _read_registry(registry_path)
    base_dir = Path(base_dir).resolve()

    scenarios: list[RegistryScenario] = []
    for _, row in df.iterrows():
        enabled = _to_bool(row.get("enabled", 0), False)
        optimize = _to_bool(row.get("optimize_storage", 0), False)
        node_id = _to_int(row.get("node_id", 0), 0)
        if node_id <= 0:
            continue

        internal_model_id = _build_internal_model_id(row)
        if not internal_model_id:
            continue

        scenario_name = str(row.get("scenario_name", "")).strip() or internal_model_id
        node_dir = _resolve_path_like(row.get("node_dir", None), base_dir) or ""
        year_model_map_file = str(row.get("year_model_map_file", "runtime_year_model_map.csv")).strip() or "runtime_year_model_map.csv"
        model_library_file = str(row.get("model_library_file", "runtime_model_library.csv")).strip() or "runtime_model_library.csv"

        tariff_path = _resolve_tariff_path(row, base_dir)
        service_calendar_path = _resolve_path_like(row.get("service_calendar_path", None), base_dir)

        scenarios.append(
            RegistryScenario(
                internal_model_id=internal_model_id,
                enabled=enabled,
                optimize=optimize,
                node_id=node_id,
                scenario_name=scenario_name,
                category=str(row.get("category", "")).strip(),
                node_dir=node_dir,
                year_model_map_file=year_model_map_file,
                model_library_file=model_library_file,
                tariff_path=tariff_path,
                service_calendar_path=service_calendar_path,
                pv_capacity_kw=_to_float(row.get("pv_capacity_kw", 0.0), 0.0),
                q_to_p_ratio=_to_float(row.get("q_to_p_ratio", 0.25), 0.25),
                transformer_capacity_kva=_to_float_or_none(row.get("transformer_capacity_kva", None)),
                transformer_pf_limit=_to_float(row.get("transformer_pf_limit", 0.95), 0.95),
                transformer_reserve_ratio=_to_float(row.get("transformer_reserve_ratio", 0.15), 0.15),
                grid_interconnection_limit_kw=_to_float_or_none(row.get("grid_interconnection_limit_kw", None)),
                device_power_max_kw=_to_float_or_none(row.get("device_power_max_kw", None)),
                search_power_min_kw=_to_float_or_none(row.get("search_power_min_kw", None)),
                search_duration_min_h=_to_float_or_none(row.get("search_duration_min_h", None)),
                search_duration_max_h=_to_float_or_none(row.get("search_duration_max_h", None)),
                include_aux_service_revenue=_to_bool(row.get("include_aux_service_revenue", 0), False),
                include_capacity_revenue=_to_bool(row.get("include_capacity_revenue", 0), False),
                include_loss_reduction_revenue=_to_bool(row.get("include_loss_reduction_revenue", 0), False),
                include_degradation_cost=_to_bool(row.get("include_degradation_cost", 1), True),
                include_government_subsidy=_to_bool(row.get("include_government_subsidy", 0), False),
                include_replacement_cost=_to_bool(row.get("include_replacement_cost", 1), True),
                dispatch_mode=str(row.get("dispatch_mode", "hybrid")).strip() or "hybrid",
                daily_demand_shadow_yuan_per_kw=_to_float(row.get("daily_demand_shadow_yuan_per_kw", 0.0), 0.0),
                voltage_penalty_coeff_yuan=_to_float(row.get("voltage_penalty_coeff_yuan", 0.0), 0.0),
                run_mode=str(row.get("run_mode", "single_user")).strip() or "single_user",
                model_year=_to_int(row.get("model_year", 2025), 2025),
                strategy_candidates=[],
                base_strategy_id="",
                extra_meta={str(k): row[k] for k in df.columns if pd.notna(row[k])},
            )
        )
    return scenarios


def _resolve_strategy_list_for_scenario(
    scenario: RegistryScenario,
    strategy_library_path: str | Path,
) -> tuple[str, list[str]]:
    strategies = load_storage_strategies(strategy_library_path)
    enabled_ids = [sid for sid, st in strategies.items() if getattr(st, "enabled", True)]
    default_ids = [
        sid for sid, st in strategies.items()
        if getattr(st, "enabled", True) and getattr(st, "is_default_candidate", True)
    ]
    candidate_ids = default_ids if default_ids else enabled_ids
    if not candidate_ids:
        raise ValueError("策略库中没有可用候选策略。")
    return candidate_ids[0], candidate_ids


def _build_service_config_for_scenario(
    scenario: RegistryScenario,
    service_config: ServiceConfig | None,
) -> ServiceConfig:
    cfg = service_config or get_default_service_config()
    meta = dict(scenario.extra_meta)

    enable_service = bool(scenario.include_aux_service_revenue or scenario.service_calendar_path)
    max_service_power_ratio = float(meta.get("max_service_power_ratio", getattr(cfg, "max_service_power_ratio", 0.30) if enable_service else 0.0))
    default_headroom_ratio = float(meta.get("default_headroom_ratio", getattr(cfg, "default_headroom_ratio", 0.15) if enable_service else 0.0))
    default_available_hours = getattr(cfg, "default_available_hours", tuple())
    if enable_service and not default_available_hours:
        default_available_hours = tuple(range(8, 22))

    return ServiceConfig(
        enable_service=enable_service,
        scenario_name="integrated_service" if enable_service else "arbitrage_only",
        service_mode="file" if (enable_service and scenario.service_calendar_path) else ("scenario" if enable_service else "none"),
        default_available_hours=tuple(default_available_hours),
        default_capacity_price_yuan_per_kw=float(meta.get("default_capacity_price_yuan_per_kw", getattr(cfg, "default_capacity_price_yuan_per_kw", 0.0) if enable_service else 0.0)),
        default_delivery_price_yuan_per_kwh=float(meta.get("default_delivery_price_yuan_per_kwh", getattr(cfg, "default_delivery_price_yuan_per_kwh", 0.0) if enable_service else 0.0)),
        default_penalty_price_yuan_per_kwh=float(meta.get("default_penalty_price_yuan_per_kwh", getattr(cfg, "default_penalty_price_yuan_per_kwh", 0.0) if enable_service else 0.0)),
        default_activation_factor=float(meta.get("default_activation_factor", getattr(cfg, "default_activation_factor", 0.15) if enable_service else 0.0)),
        max_service_power_ratio=max(0.0, max_service_power_ratio if enable_service else 0.0),
        require_headroom=bool(meta.get("require_headroom", getattr(cfg, "require_headroom", True) if enable_service else False)),
        default_headroom_ratio=max(0.0, default_headroom_ratio if enable_service else 0.0),
        delivery_score_floor=float(meta.get("delivery_score_floor", getattr(cfg, "delivery_score_floor", 0.90) if enable_service else 1.0)),
    )


def _to_optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
    except Exception:
        return None
    return out if np.isfinite(out) else None


def _first_optional_float(*values: Any) -> float | None:
    for value in values:
        parsed = _to_optional_float(value)
        if parsed is not None:
            return parsed
    return None


def _apply_frontend_economic_overrides(ctx: AnnualOperationContext) -> AnnualOperationContext:
    meta = dict(ctx.meta)
    direct_degradation = _to_optional_float(meta.get("degradation_cost_yuan_per_kwh_throughput"))
    battery_capex_share = _to_optional_float(meta.get("battery_capex_share"))
    cycle_life_efc = _to_optional_float(meta.get("cycle_life_efc"))
    annual_cycle_limit = _to_optional_float(meta.get("annual_cycle_limit"))

    for strategy in ctx.strategy_library.values():
        strategy_cycle_life = _first_optional_float(
            cycle_life_efc,
            getattr(strategy, "cycle_life_efc", None),
            strategy.metadata.get("cycle_life_efc") if isinstance(strategy.metadata, dict) else None,
        )
        if annual_cycle_limit is not None and annual_cycle_limit > 0:
            strategy.annual_cycle_limit = float(annual_cycle_limit)

        if direct_degradation is not None:
            strategy.degradation_cost_yuan_per_kwh_throughput = max(0.0, direct_degradation)
        elif (
            float(getattr(strategy, "degradation_cost_yuan_per_kwh_throughput", 0.0)) <= 0
            and battery_capex_share is not None
            and strategy_cycle_life is not None
            and strategy_cycle_life > 0
        ):
            energy_capex = max(0.0, float(getattr(strategy, "capex_energy_yuan_per_kwh", 0.0)))
            strategy.degradation_cost_yuan_per_kwh_throughput = max(
                0.0,
                energy_capex * max(0.0, battery_capex_share) / (2.0 * strategy_cycle_life),
            )

    if ctx.strategy.strategy_id in ctx.strategy_library:
        ctx.strategy = ctx.strategy_library[ctx.strategy.strategy_id]
    return ctx


def build_context_from_registry_scenario(
    scenario: RegistryScenario,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    operation_config: OperationConfig | None = None,
    safety_config: SafetyConfig | None = None,
    service_config: ServiceConfig | None = None,
) -> AnnualOperationContext:
    base_strategy_id, candidate_ids = _resolve_strategy_list_for_scenario(scenario, strategy_library_path)
    scenario.base_strategy_id = base_strategy_id
    scenario.strategy_candidates = candidate_ids

    scenario_service_config = _build_service_config_for_scenario(scenario, service_config)

    demand_charge = _to_float(
        scenario.extra_meta.get("demand_charge_yuan_per_kw_month", scenario.daily_demand_shadow_yuan_per_kw),
        scenario.daily_demand_shadow_yuan_per_kw,
    )

    ctx = build_annual_operation_context(
        internal_model_id=scenario.internal_model_id,
        strategy_id=base_strategy_id,
        node_dir=scenario.node_dir,
        year_model_map_file=scenario.year_model_map_file,
        model_library_file=scenario.model_library_file,
        tariff_path=scenario.tariff_path,
        strategy_library_path=str(strategy_library_path),
        service_calendar_path=scenario.service_calendar_path,
        transformer_capacity_kva=scenario.transformer_capacity_kva,
        transformer_pf_limit=scenario.transformer_pf_limit,
        transformer_reserve_ratio=scenario.transformer_reserve_ratio,
        operation_config=operation_config or get_default_operation_config(),
        safety_config=safety_config or get_default_safety_config(),
        service_config=scenario_service_config,
        q_to_p_ratio=scenario.q_to_p_ratio,
        pv_capacity_kw=scenario.pv_capacity_kw,
        node_id=scenario.node_id,
        scenario_name=scenario.scenario_name,
        category=scenario.category,
        model_year=scenario.model_year,
        include_aux_service_revenue=scenario.include_aux_service_revenue,
        include_capacity_revenue=scenario.include_capacity_revenue,
        include_loss_reduction_revenue=scenario.include_loss_reduction_revenue,
        include_degradation_cost=scenario.include_degradation_cost,
        include_government_subsidy=scenario.include_government_subsidy,
        include_replacement_cost=scenario.include_replacement_cost,
        daily_demand_charge_yuan_per_kw=demand_charge,
        voltage_penalty_coeff_yuan=scenario.voltage_penalty_coeff_yuan,
        dispatch_mode=scenario.dispatch_mode,
        run_mode=scenario.run_mode,
        extra_meta=scenario.extra_meta,
    )
    return _apply_frontend_economic_overrides(ctx)


def build_search_spaces_for_scenario(
    scenario: RegistryScenario,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    context: AnnualOperationContext | None = None,
) -> dict[str, SearchSpaceConfig]:
    base_strategy_id, candidate_ids = _resolve_strategy_list_for_scenario(scenario, strategy_library_path)
    scenario.base_strategy_id = base_strategy_id
    scenario.strategy_candidates = candidate_ids

    strategies = load_storage_strategies(strategy_library_path)
    out: dict[str, SearchSpaceConfig] = {}
    boundary_records: dict[str, dict[str, Any]] = {}

    for sid in candidate_ids:
        st = strategies[sid]
        if context is None:
            single_power = _first_optional_float(getattr(st, "rated_power_kw_single", None)) or 1.0
            power_min = scenario.search_power_min_kw or min(single_power, scenario.device_power_max_kw or single_power)
            power_max = scenario.device_power_max_kw or scenario.grid_interconnection_limit_kw or single_power
            duration_min = max(float(st.duration_min_h), float(scenario.search_duration_min_h or st.duration_min_h))
            duration_max = min(float(st.duration_max_h), float(scenario.search_duration_max_h or st.duration_max_h))
        else:
            boundary = compute_storage_configuration_boundary(
                ctx=context,
                strategy=st,
                explicit_power_min_kw=scenario.search_power_min_kw,
                explicit_power_max_kw=scenario.device_power_max_kw,
                grid_interconnection_limit_kw=scenario.grid_interconnection_limit_kw,
                explicit_duration_min_h=scenario.search_duration_min_h,
                explicit_duration_max_h=scenario.search_duration_max_h,
            )
            boundary_records[sid] = boundary.as_dict()
            if not boundary.is_feasible:
                raise ValueError(
                    f"场景 {scenario.internal_model_id} / 策略 {sid} 的储能配置边界不可行："
                    + "；".join(boundary.errors)
                )
            power_min = boundary.power_min_kw
            power_max = boundary.power_max_kw
            duration_min = boundary.duration_min_h
            duration_max = boundary.duration_max_h

        out[sid] = SearchSpaceConfig(
            power_min_kw=max(1e-6, float(power_min)),
            power_max_kw=max(max(1e-6, float(power_min)), float(power_max)),
            duration_min_h=max(0.1, float(duration_min)),
            duration_max_h=max(max(0.1, float(duration_min)), float(duration_max)),
        )

    if context is not None:
        context.meta["configuration_boundaries"] = boundary_records

    return out
