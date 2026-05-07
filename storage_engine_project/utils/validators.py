from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


def _read(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def validate_1d_array(
    values: Sequence[float] | np.ndarray,
    name: str,
    expected_size: int | None = None,
    allow_negative: bool = True,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)

    if expected_size is not None and arr.size != expected_size:
        raise ValueError(f"{name} 长度应为 {expected_size}，当前为 {arr.size}。")

    if np.any(~np.isfinite(arr)):
        raise ValueError(f"{name} 中存在非有限值。")

    if not allow_negative and np.any(arr < 0):
        raise ValueError(f"{name} 中存在负值。")

    return arr


def validate_2d_array(
    values: Sequence[Sequence[float]] | np.ndarray,
    name: str,
    expected_shape: tuple[int, int] | None = None,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)

    if arr.ndim != 2:
        raise ValueError(f"{name} 必须为二维数组，当前 ndim={arr.ndim}。")

    if expected_shape is not None and tuple(arr.shape) != tuple(expected_shape):
        raise ValueError(f"{name} 形状应为 {expected_shape}，当前为 {arr.shape}。")

    if np.any(~np.isfinite(arr)):
        raise ValueError(f"{name} 中存在非有限值。")

    return arr


def validate_price_vector(price_vector: Sequence[float] | np.ndarray) -> np.ndarray:
    arr = validate_1d_array(
        price_vector,
        name="price_vector",
        expected_size=24,
        allow_negative=False,
    )

    if np.all(arr <= 0):
        raise ValueError("price_vector 全部小于等于 0，不合理。")

    return arr


def validate_profile_24h(
    profile: Sequence[float] | np.ndarray,
    name: str,
    allow_negative: bool = False,
) -> np.ndarray:
    return validate_1d_array(
        profile,
        name=name,
        expected_size=24,
        allow_negative=allow_negative,
    )


def validate_config_vector(
    config: Sequence[float] | np.ndarray,
    require_positive: bool = True,
) -> np.ndarray:
    arr = np.asarray(config, dtype=float).reshape(-1)

    if arr.size != 2:
        raise ValueError(
            "config 必须严格为 [P_kW, E_kWh] 两个元素。"
            f"当前收到 {arr.size} 个元素：{arr.tolist()}"
        )

    if np.any(~np.isfinite(arr)):
        raise ValueError("config 中存在非有限值。")

    if require_positive:
        if arr[0] <= 0:
            raise ValueError("储能功率 P 必须大于 0。")
        if arr[1] <= 0:
            raise ValueError("储能容量 E 必须大于 0。")

    return arr.copy()


def validate_tariff_payload(tariff_payload: Any) -> None:
    tariff_list = _read(tariff_payload, "tariff_list")
    price_year_matrix = _read(tariff_payload, "price_year_matrix")
    year_period_index = _read(tariff_payload, "year_period_index")
    price_e = _read(tariff_payload, "price_e")

    if tariff_list is None or len(tariff_list) == 0:
        raise ValueError("tariff_payload 中 tariff_list 为空。")

    price_year_matrix = validate_2d_array(price_year_matrix, name="price_year_matrix")
    if price_year_matrix.shape[1] != 24:
        raise ValueError("price_year_matrix 列数必须为 24。")
    if np.any(price_year_matrix < 0):
        raise ValueError("price_year_matrix 中存在负值。")

    year_period_index_arr = validate_1d_array(
        year_period_index,
        name="year_period_index",
        expected_size=price_year_matrix.shape[0],
        allow_negative=False,
    )

    if np.any(np.abs(year_period_index_arr - np.round(year_period_index_arr)) > 1e-9):
        raise ValueError("year_period_index 必须全部为整数索引。")

    year_period_index_int = np.round(year_period_index_arr).astype(int)
    if np.any(year_period_index_int >= len(tariff_list)):
        bad_vals = sorted(set(year_period_index_int[year_period_index_int >= len(tariff_list)].tolist()))
        raise ValueError(
            f"year_period_index 中存在超出 tariff_list 范围的索引，"
            f"最大允许值为 {len(tariff_list) - 1}，实际出现：{bad_vals[:10]}"
        )

    validate_price_vector(price_e)

    for idx, item in enumerate(tariff_list):
        name = _read(item, "name", default=f"period_{idx}")
        days = int(_read(item, "days", default=0))
        price_vector_i = _read(item, "price_vector", default=None)

        if days <= 0:
            raise ValueError(f"tariff_list[{idx}] ({name}) 的 days 必须大于 0。")
        validate_price_vector(price_vector_i)


def validate_dss_payload(dss_payload: Any) -> None:
    """
    校验 OpenDSS 配置结构。
    当前工程只允许运行时负荷文件，不再允许 loads_base_dss_path 和默认负荷参数。
    """
    required_path_fields = [
        "master_dss_path",
        "runtime_loads_dss_path",
        "storage_case_dss_path",
        "tielines_dss_path",
        "topology_case_dss_path",
        "lines_main_dss_path",
    ]

    for field_name in required_path_fields:
        path_str = str(_read(dss_payload, field_name, default="")).strip()
        if not path_str:
            raise ValueError(f"dss.{field_name} 缺失。")
        if not Path(path_str).exists():
            raise FileNotFoundError(f"dss.{field_name} 不存在：{path_str}")

    bus_count = int(_read(dss_payload, "bus_count", default=0))
    load_node_count = int(_read(dss_payload, "load_node_count", default=0))
    slack_bus = int(_read(dss_payload, "slack_bus", default=0))
    base_mva = float(_read(dss_payload, "base_mva", default=-1))
    base_kv = float(_read(dss_payload, "base_kv", default=-1))
    v_min = float(_read(dss_payload, "voltage_min_pu", default=-1))
    v_max = float(_read(dss_payload, "voltage_max_pu", default=-1))
    source_bus_name = str(_read(dss_payload, "source_bus_name", default="")).strip()

    if bus_count <= 0:
        raise ValueError("dss.bus_count 必须大于 0。")
    if load_node_count <= 0:
        raise ValueError("dss.load_node_count 必须大于 0。")
    if load_node_count >= bus_count:
        raise ValueError("dss.load_node_count 应小于 bus_count（源点不应计入负荷节点）。")
    if slack_bus < 1 or slack_bus > bus_count:
        raise ValueError("dss.slack_bus 超出节点范围。")
    if base_mva <= 0:
        raise ValueError("dss.base_mva 必须大于 0。")
    if base_kv <= 0:
        raise ValueError("dss.base_kv 必须大于 0。")
    if not (0 < v_min < v_max):
        raise ValueError("dss 电压上下限设置错误。")
    if not source_bus_name:
        raise ValueError("dss.source_bus_name 不能为空。")


def validate_network_payload(network_payload: Any) -> None:
    bus_count = int(_read(network_payload, "bus_count", default=0))
    load_node_count = int(_read(network_payload, "load_node_count", default=0))
    slack_bus = int(_read(network_payload, "slack_bus", default=0))
    base_mva = float(_read(network_payload, "base_mva", default=-1))
    base_kv = float(_read(network_payload, "base_kv", default=-1))
    v_min = float(_read(network_payload, "voltage_min_pu", default=-1))
    v_max = float(_read(network_payload, "voltage_max_pu", default=-1))
    source_bus_name = str(_read(network_payload, "source_bus_name", default="")).strip()

    if bus_count <= 0:
        raise ValueError("network.bus_count 必须大于 0。")
    if load_node_count <= 0:
        raise ValueError("network.load_node_count 必须大于 0。")
    if load_node_count >= bus_count:
        raise ValueError("network.load_node_count 应小于 bus_count。")
    if slack_bus < 1 or slack_bus > bus_count:
        raise ValueError("network.slack_bus 超出节点范围。")
    if base_mva <= 0:
        raise ValueError("network.base_mva 必须大于 0。")
    if base_kv <= 0:
        raise ValueError("network.base_kv 必须大于 0。")
    if not (0 < v_min < v_max):
        raise ValueError("network 电压上下限设置错误。")
    if not source_bus_name:
        raise ValueError("network.source_bus_name 不能为空。")


def validate_finance_payload(finance_payload: Any) -> None:
    storage = _read(finance_payload, "storage")
    economics = _read(finance_payload, "economics")

    if storage is None:
        raise ValueError("finance.storage 缺失。")
    if economics is None:
        raise ValueError("finance.economics 缺失。")

    eta_charge = float(_read(storage, "eta_charge", default=-1))
    eta_discharge = float(_read(storage, "eta_discharge", default=-1))
    soc_min = float(_read(storage, "soc_min", default=-1))
    soc_max = float(_read(storage, "soc_max", default=-1))
    soc_init = float(_read(storage, "soc_init", default=-1))
    candidate_durations = validate_1d_array(
        _read(storage, "candidate_durations_h"),
        name="candidate_durations_h",
        allow_negative=False,
    )

    if not (0 < eta_charge <= 1):
        raise ValueError("finance.storage.eta_charge 必须位于 (0,1]。")
    if not (0 < eta_discharge <= 1):
        raise ValueError("finance.storage.eta_discharge 必须位于 (0,1]。")
    if not (0 <= soc_min < soc_max <= 1):
        raise ValueError("finance.storage 的 SOC 上下限设置错误。")
    if not (soc_min <= soc_init <= soc_max):
        raise ValueError("finance.storage.soc_init 必须位于 [soc_min, soc_max]。")
    if candidate_durations.size == 0:
        raise ValueError("candidate_durations_h 不能为空。")

    discount_rate = float(_read(economics, "discount_rate", default=-1))
    lifetime_years = int(_read(economics, "lifetime_years", default=0))
    maintenance_rate = float(_read(economics, "maintenance_rate", default=0.0))
    price_aux = float(_read(economics, "auxiliary_service_price_yuan_per_kwh", default=0.0))
    price_cap = float(_read(economics, "capacity_service_price_yuan_per_kw_day", default=0.0))
    price_demand = float(_read(economics, "demand_charge_yuan_per_kw_month", default=0.0))
    price_loss = float(_read(economics, "network_loss_price_yuan_per_kwh", default=0.0))

    if discount_rate < 0:
        raise ValueError("finance.economics.discount_rate 不能为负。")
    if lifetime_years <= 0:
        raise ValueError("finance.economics.lifetime_years 必须大于 0。")
    if maintenance_rate < 0:
        raise ValueError("finance.economics.maintenance_rate 不能为负。")
    if price_aux < 0:
        raise ValueError("auxiliary_service_price_yuan_per_kwh 不能为负。")
    if price_cap < 0:
        raise ValueError("capacity_service_price_yuan_per_kw_day 不能为负。")
    if price_demand < 0:
        raise ValueError("demand_charge_yuan_per_kw_month 不能为负。")
    if price_loss < 0:
        raise ValueError("network_loss_price_yuan_per_kwh 不能为负。")


def validate_runtime_payload(runtime_payload: Any) -> None:
    days_per_year = int(_read(runtime_payload, "days_per_year", default=0))
    hours_per_day = int(_read(runtime_payload, "hours_per_day", default=0))
    model_library = _read(runtime_payload, "model_library", default=None)
    year_model_map = _read(runtime_payload, "year_model_map", default=None)
    network_runtime_db = _read(runtime_payload, "network_runtime_db", default=None)
    runtime_node_count = int(_read(runtime_payload, "runtime_node_count", default=0))
    strict_runtime_only = bool(_read(runtime_payload, "strict_runtime_only", default=False))

    if days_per_year <= 0:
        raise ValueError("runtime.days_per_year 必须大于 0。")
    if hours_per_day != 24:
        raise ValueError("当前工程仅支持 24 点小时级 runtime。")
    if not strict_runtime_only:
        raise ValueError("当前工程要求 runtime.strict_runtime_only=True。")

    if model_library is None or not isinstance(model_library, dict) or not model_library:
        raise ValueError("runtime.model_library 不能为空。")

    year_model_map_arr = validate_1d_array(
        year_model_map,
        name="runtime.year_model_map",
        expected_size=days_per_year,
        allow_negative=False,
    )
    if np.any(np.abs(year_model_map_arr - np.round(year_model_map_arr)) > 1e-9):
        raise ValueError("runtime.year_model_map 必须为整数编号。")

    for model_id, profile in model_library.items():
        _ = model_id
        validate_profile_24h(profile, name=f"runtime.model_library[{model_id}]", allow_negative=False)

    if network_runtime_db is None or not isinstance(network_runtime_db, dict):
        raise ValueError("runtime.network_runtime_db 缺失或格式错误。")
    if runtime_node_count <= 0:
        raise ValueError("runtime.runtime_node_count 必须大于 0。")
    if len(network_runtime_db) != runtime_node_count:
        raise ValueError(
            f"runtime.network_runtime_db 节点数与 runtime_node_count 不一致："
            f"{len(network_runtime_db)} != {runtime_node_count}"
        )


def validate_case(case: Any) -> None:
    if case is None:
        raise ValueError("case 不能为空。")

    scenario = _read(case, "scenario")
    tariff = _read(case, "tariff")
    finance = _read(case, "finance")
    runtime = _read(case, "runtime")
    dss = _read(case, "dss")
    network = _read(case, "network")

    if scenario is None:
        raise ValueError("case.scenario 缺失。")
    if tariff is None:
        raise ValueError("case.tariff 缺失。")
    if finance is None:
        raise ValueError("case.finance 缺失。")
    if runtime is None:
        raise ValueError("case.runtime 缺失。")
    if dss is None:
        raise ValueError("case.dss 缺失。")
    if network is None:
        raise ValueError("case.network 缺失。")

    target_node = int(_read(case, "target_node", default=_read(scenario, "target_node", default=0)))
    target_bus_name = str(_read(case, "target_bus_name", default=_read(scenario, "target_bus_name", default=""))).strip()
    target_element_bus = str(_read(case, "target_element_bus", default=_read(scenario, "target_element_bus", default=""))).strip()
    target_load_name = str(_read(case, "target_load_name", default=_read(scenario, "target_load_name", default=""))).strip()

    if target_node <= 0:
        raise ValueError("case.target_node 必须大于 0。")
    if not target_bus_name:
        raise ValueError("case.target_bus_name 不能为空。")
    if not target_element_bus:
        raise ValueError("case.target_element_bus 不能为空。")
    if not target_load_name:
        raise ValueError("case.target_load_name 不能为空。")

    validate_tariff_payload(tariff)
    validate_finance_payload(finance)
    validate_runtime_payload(runtime)
    validate_dss_payload(dss)
    validate_network_payload(network)

    price_year_matrix = validate_2d_array(
        _read(case, "price_year_matrix"),
        name="case.price_year_matrix",
    )
    if price_year_matrix.shape[1] != 24:
        raise ValueError("case.price_year_matrix 列数必须为 24。")

    model_library = _read(case, "model_library", default=None)
    year_model_map = _read(case, "year_model_map", default=None)
    if model_library is None or not isinstance(model_library, dict) or not model_library:
        raise ValueError("case.model_library 缺失或为空。")

    year_model_map_arr = validate_1d_array(
        year_model_map,
        name="case.year_model_map",
        expected_size=price_year_matrix.shape[0],
        allow_negative=False,
    )
    if np.any(np.abs(year_model_map_arr - np.round(year_model_map_arr)) > 1e-9):
        raise ValueError("case.year_model_map 必须为整数。")

    optimization_reference_profile = _read(case, "optimization_reference_profile_kw", default=None)
    if optimization_reference_profile is not None:
        validate_profile_24h(
            optimization_reference_profile,
            name="case.optimization_reference_profile_kw",
            allow_negative=False,
        )

    active_node_ids = _read(case, "active_node_ids", default=None)
    network_runtime_db = _read(case, "network_runtime_db", default=None)
    if active_node_ids is not None and network_runtime_db is not None:
        active_node_arr = np.asarray(active_node_ids, dtype=int).reshape(-1)
        runtime_node_ids = np.asarray(sorted(int(k) for k in network_runtime_db.keys()), dtype=int)
        if active_node_arr.size == 0:
            raise ValueError("case.active_node_ids 不能为空。")
        if len(np.unique(active_node_arr)) != active_node_arr.size:
            raise ValueError("case.active_node_ids 中存在重复节点编号。")
        if not np.array_equal(np.sort(active_node_arr), runtime_node_ids):
            raise ValueError("case.active_node_ids 与 network_runtime_db 键集合不一致。")


def validate_summary_rows(summary_rows: Sequence[Mapping[str, Any]]) -> None:
    if summary_rows is None:
        raise ValueError("summary_rows 不能为空。")
    if len(summary_rows) == 0:
        raise ValueError("summary_rows 为空，说明当前没有任何场景成功完成。")

    required_fields = [
        "scenario",
        "node",
        "power_kw",
        "energy_kwh",
        "duration_h",
        "npv_wan",
        "payback_years",
        "irr_percent",
        "initial_capex_yuan",
        "annual_operating_revenue_yuan",
        "annual_net_cashflow_yuan",
        "annual_equivalent_cycles",
    ]

    for idx, row in enumerate(summary_rows):
        for field in required_fields:
            if field not in row:
                raise ValueError(f"summary_rows[{idx}] 缺少字段：{field}")

        if float(row["power_kw"]) <= 0:
            raise ValueError(f"summary_rows[{idx}].power_kw 必须大于 0。")
        if float(row["energy_kwh"]) <= 0:
            raise ValueError(f"summary_rows[{idx}].energy_kwh 必须大于 0。")