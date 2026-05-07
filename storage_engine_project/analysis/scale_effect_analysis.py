from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from storage_engine_project.economics.financial_evaluator import evaluate_financials
from storage_engine_project.models.result_models import ScaleEffectPoint, ScaleEffectResult
from storage_engine_project.optimization.optimization_models import get_cached_annual_result
from storage_engine_project.simulation.annual_simulator import run_annual_simulation


def _read(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _safe_float(
    value: Any,
    name: str,
    *,
    default: float | None = None,
    allow_negative: bool = True,
) -> float:
    if value is None:
        if default is None:
            raise ValueError(f"{name} 为空，无法转换为 float。")
        value = default

    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{name} 无法转换为 float，原值={value!r}。") from exc

    if not np.isfinite(out):
        raise ValueError(f"{name} 不是有限值，当前为 {out!r}。")
    if (not allow_negative) and out < 0:
        raise ValueError(f"{name} 不能为负，当前为 {out}。")
    return out


def _validate_base_config(base_config: Sequence[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(base_config, dtype=float).reshape(-1)

    if arr.size != 2:
        raise ValueError(
            "base_config 必须严格为 [P_kW, E_kWh] 两个元素，"
            f"当前收到 {arr.size} 个元素：{arr.tolist()}"
        )

    if np.any(~np.isfinite(arr)):
        raise ValueError("base_config 中存在非有限值。")

    power_kw = float(arr[0])
    energy_kwh = float(arr[1])

    if power_kw <= 0:
        raise ValueError("base_config 中的功率 P_kW 必须大于 0。")
    if energy_kwh <= 0:
        raise ValueError("base_config 中的容量 E_kWh 必须大于 0。")

    return np.asarray([power_kw, energy_kwh], dtype=float)


def _normalize_replacement_years(value: Any) -> tuple[int, ...]:
    if value is None:
        return tuple()

    if isinstance(value, np.ndarray):
        seq = value.reshape(-1).tolist()
    elif isinstance(value, (list, tuple, set)):
        seq = list(value)
    else:
        seq = [value]

    years: list[int] = []
    for item in seq:
        if item is None:
            continue
        try:
            year = int(item)
        except Exception as exc:
            raise ValueError(f"replacement_years 中存在无法转换为 int 的值：{item!r}") from exc
        if year <= 0:
            raise ValueError(f"replacement_years 中的年份必须为正整数，当前为 {year}")
        years.append(year)

    return tuple(years)


def generate_scale_factors(
    n_points: int,
    scale_min: float,
    scale_max: float,
    spacing: str = "linear",
) -> np.ndarray:
    if n_points < 2:
        raise ValueError("n_points 至少应为 2。")
    if scale_min <= 0:
        raise ValueError("scale_min 必须大于 0。")
    if scale_max < scale_min:
        raise ValueError("scale_max 必须不小于 scale_min。")

    spacing = str(spacing).strip().lower()
    if spacing not in {"linear", "log"}:
        raise ValueError("spacing 仅支持 'linear' 或 'log'。")

    if spacing == "log":
        return np.geomspace(scale_min, scale_max, num=n_points, dtype=float)

    return np.linspace(scale_min, scale_max, num=n_points, dtype=float)


def evaluate_scale_point(
    case: Any,
    base_config: Sequence[float] | np.ndarray,
    scale_factor: float,
) -> ScaleEffectPoint:
    scale_factor = _safe_float(scale_factor, "scale_factor", allow_negative=False)
    if scale_factor <= 0:
        raise ValueError("scale_factor 必须大于 0。")

    base_arr = _validate_base_config(base_config)
    power_kw = float(base_arr[0] * scale_factor)
    energy_kwh = float(base_arr[1] * scale_factor)
    duration_h = float(energy_kwh / power_kw)

    config_vec = np.asarray([power_kw, energy_kwh], dtype=float)

    try:
        annual_result = get_cached_annual_result(case, config_vec)
        if annual_result is None:
            annual_result = run_annual_simulation(
                ctx=case.context if hasattr(case, "context") else case,
                rated_power_kw=power_kw,
                rated_energy_kwh=energy_kwh,
            )

        financial_result = evaluate_financials(
            ctx=case.context if hasattr(case, "context") else case,
            annual_result=annual_result,
        )
    except Exception as exc:
        raise RuntimeError(
            f"规模效应点计算失败：scale_factor={scale_factor:.6f}, "
            f"P={power_kw:.4f} kW, E={energy_kwh:.4f} kWh。"
        ) from exc

    duration_h_out = _safe_float(
        _read(financial_result, "duration_h", default=duration_h),
        "duration_h",
        default=duration_h,
        allow_negative=False,
    )
    capex_yuan = _safe_float(
        _read(financial_result, "initial_capex_yuan", default=0.0),
        "initial_capex_yuan",
        default=0.0,
        allow_negative=False,
    )
    government_subsidy_yuan = _safe_float(
        _read(financial_result, "government_subsidy_yuan", default=0.0),
        "government_subsidy_yuan",
        default=0.0,
        allow_negative=False,
    )
    net_initial_capex_yuan = _safe_float(
        _read(financial_result, "net_initial_capex_yuan", default=capex_yuan),
        "net_initial_capex_yuan",
        default=capex_yuan,
        allow_negative=False,
    )
    npv_yuan = _safe_float(
        _read(financial_result, "npv_yuan", default=0.0),
        "npv_yuan",
        default=0.0,
        allow_negative=True,
    )
    payback_years = _safe_float(
        _read(financial_result, "simple_payback_years", "payback_years", default=np.inf),
        "payback_years",
        default=np.inf,
        allow_negative=False,
    )
    irr_percent = _safe_float(
        _read(financial_result, "irr", "irr_percent", default=0.0),
        "irr_percent",
        default=0.0,
        allow_negative=True,
    )
    annual_cycles = _safe_float(
        _read(
            financial_result,
            "annual_equivalent_cycles",
            default=_read(annual_result, "annual_equivalent_full_cycles", default=0.0),
        ),
        "annual_equivalent_cycles",
        default=0.0,
        allow_negative=False,
    )

    annual_arbitrage_revenue_yuan = _safe_float(
        _read(annual_result, "annual_arbitrage_revenue_yuan", default=0.0),
        "annual_arbitrage_revenue_yuan",
        default=0.0,
        allow_negative=True,
    )
    annual_demand_saving_yuan = _safe_float(
        _read(annual_result, "annual_demand_saving_yuan", default=0.0),
        "annual_demand_saving_yuan",
        default=0.0,
        allow_negative=True,
    )
    annual_aux_service_revenue_yuan = _safe_float(
        _read(annual_result, "annual_service_capacity_revenue_yuan", default=0.0)
        + _read(annual_result, "annual_service_delivery_revenue_yuan", default=0.0),
        "annual_aux_service_revenue_yuan",
        default=0.0,
        allow_negative=True,
    )
    annual_capacity_revenue_yuan = _safe_float(
        _read(annual_result, "annual_capacity_revenue_yuan", default=0.0),
        "annual_capacity_revenue_yuan",
        default=0.0,
        allow_negative=True,
    )
    annual_loss_reduction_revenue_yuan = _safe_float(
        _read(annual_result, "annual_loss_reduction_revenue_yuan", default=0.0),
        "annual_loss_reduction_revenue_yuan",
        default=0.0,
        allow_negative=True,
    )
    annual_voltage_penalty_yuan = _safe_float(
        _read(annual_result, "annual_voltage_penalty_yuan", default=0.0),
        "annual_voltage_penalty_yuan",
        default=0.0,
        allow_negative=False,
    )
    annual_operating_revenue_yuan = _safe_float(
        _read(
            financial_result,
            "annualized_net_cashflow_yuan",
            "annual_operating_revenue_yuan",
            default=(
                annual_arbitrage_revenue_yuan
                + annual_demand_saving_yuan
                + annual_aux_service_revenue_yuan
                + annual_capacity_revenue_yuan
                + annual_loss_reduction_revenue_yuan
                - annual_voltage_penalty_yuan
            ),
        ),
        "annual_operating_revenue_yuan",
        allow_negative=True,
    )
    annual_fixed_maintenance_cost_yuan = _safe_float(
        _read(financial_result, "annual_fixed_maintenance_cost_yuan", default=0.0),
        "annual_fixed_maintenance_cost_yuan",
        default=0.0,
        allow_negative=False,
    )
    annual_variable_maintenance_cost_yuan = _safe_float(
        _read(financial_result, "annual_variable_maintenance_cost_yuan", default=0.0),
        "annual_variable_maintenance_cost_yuan",
        default=0.0,
        allow_negative=False,
    )
    annual_maintenance_cost_yuan = _safe_float(
        _read(financial_result, "annual_maintenance_cost_yuan", default=0.0),
        "annual_maintenance_cost_yuan",
        default=0.0,
        allow_negative=False,
    )
    annual_degradation_cost_yuan = _safe_float(
        _read(annual_result, "annual_degradation_cost_yuan", default=0.0),
        "annual_degradation_cost_yuan",
        default=0.0,
        allow_negative=False,
    )
    annual_replacement_reserve_cost_yuan = _safe_float(
        _read(financial_result, "annual_replacement_reserve_cost_yuan", default=0.0),
        "annual_replacement_reserve_cost_yuan",
        default=0.0,
        allow_negative=False,
    )
    annual_net_cashflow_yuan = _safe_float(
        _read(financial_result, "annualized_net_cashflow_yuan", "annual_net_cashflow_yuan", default=0.0),
        "annual_net_cashflow_yuan",
        default=0.0,
        allow_negative=True,
    )

    replacement_years = _normalize_replacement_years(
        _read(financial_result, "replacement_years", default=tuple())
    )

    return ScaleEffectPoint(
        scale_factor=float(scale_factor),
        power_kw=power_kw,
        energy_kwh=energy_kwh,
        duration_h=duration_h_out,
        capex_yuan=capex_yuan,
        government_subsidy_yuan=government_subsidy_yuan,
        net_initial_capex_yuan=net_initial_capex_yuan,
        npv_yuan=npv_yuan,
        payback_years=payback_years,
        irr_percent=irr_percent,
        annual_cycles=annual_cycles,
        annual_arbitrage_revenue_yuan=annual_arbitrage_revenue_yuan,
        annual_demand_saving_yuan=annual_demand_saving_yuan,
        annual_aux_service_revenue_yuan=annual_aux_service_revenue_yuan,
        annual_capacity_revenue_yuan=annual_capacity_revenue_yuan,
        annual_loss_reduction_revenue_yuan=annual_loss_reduction_revenue_yuan,
        annual_voltage_penalty_yuan=annual_voltage_penalty_yuan,
        annual_operating_revenue_yuan=annual_operating_revenue_yuan,
        annual_fixed_maintenance_cost_yuan=annual_fixed_maintenance_cost_yuan,
        annual_variable_maintenance_cost_yuan=annual_variable_maintenance_cost_yuan,
        annual_maintenance_cost_yuan=annual_maintenance_cost_yuan,
        annual_degradation_cost_yuan=annual_degradation_cost_yuan,
        annual_replacement_reserve_cost_yuan=annual_replacement_reserve_cost_yuan,
        annual_net_cashflow_yuan=annual_net_cashflow_yuan,
        replacement_years=replacement_years,
    )


def run_scale_effect_analysis(
    case: Any,
    base_config: Sequence[float] | np.ndarray,
    n_points: int = 50,
    scale_min: float = 0.20,
    scale_max: float = 3.00,
    spacing: str = "linear",
) -> ScaleEffectResult:
    base_arr = _validate_base_config(base_config)
    scale_factors = generate_scale_factors(
        n_points=n_points,
        scale_min=scale_min,
        scale_max=scale_max,
        spacing=spacing,
    )

    points: list[ScaleEffectPoint] = []
    for factor in scale_factors:
        point = evaluate_scale_point(
            case=case,
            base_config=base_arr,
            scale_factor=float(factor),
        )
        points.append(point)

    return ScaleEffectResult(points=tuple(points))


def scale_result_to_table(
    scale_result: ScaleEffectResult,
) -> list[dict[str, float | int | list[int]]]:
    rows: list[dict[str, float | int | list[int]]] = []

    for point in scale_result.points:
        row = dict(point.to_dict())
        row["replacement_years"] = list(point.replacement_years)
        row["annual_equivalent_cycles"] = float(point.annual_cycles)
        rows.append(row)

    return rows
