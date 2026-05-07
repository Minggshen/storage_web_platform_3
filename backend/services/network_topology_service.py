from __future__ import annotations

from typing import List

from models.project_model import EdgeType, NodeType, TopologyCatalogItem


class NetworkTopologyService:
    """Provide topology editor metadata for the phase-2 front-end canvas."""

    def get_node_catalog(self) -> List[TopologyCatalogItem]:
        return [
            TopologyCatalogItem(
                type=NodeType.GRID.value,
                label="电网/电源",
                required_params=["base_kv", "pu"],
                recommended_params=["short_circuit_mva", "source_bus"],
                notes=["作为上级电网等值电源；DSS 编译时映射到 sourcebus"],
            ),
            TopologyCatalogItem(
                type=NodeType.TRANSFORMER.value,
                label="主变",
                required_params=["rated_kva", "voltage_level_kv"],
                recommended_params=["reserve_ratio", "power_factor_limit"],
                notes=["建议作为画布主电源起点", "后续可扩展为多主变场景"],
            ),
            TopologyCatalogItem(
                type=NodeType.DISTRIBUTION_TRANSFORMER.value,
                label="用户配变",
                required_params=["rated_kva", "primary_voltage_kv", "voltage_level_kv"],
                recommended_params=["primary_bus_name", "secondary_bus_name", "xhl_percent", "percent_r", "tap"],
                notes=["用于表达工商业用户从 10kV 到 0.4kV 的配变接入"],
            ),
            TopologyCatalogItem(
                type=NodeType.BUS.value,
                label="母线",
                required_params=["voltage_level_kv"],
                recommended_params=["bus_role"],
                notes=["用于表示 10kV 母线或中间连接点"],
            ),
            TopologyCatalogItem(
                type=NodeType.RING_MAIN_UNIT.value,
                label="环网柜",
                required_params=[],
                recommended_params=["cabinet_code"],
                notes=["当前阶段主要用于示意与拓扑连接"],
            ),
            TopologyCatalogItem(
                type=NodeType.BRANCH.value,
                label="分支点",
                required_params=["voltage_level_kv"],
                recommended_params=["dss_bus_name"],
                notes=["用于表示馈线分支或中间连接点"],
            ),
            TopologyCatalogItem(
                type=NodeType.SWITCH.value,
                label="开关",
                required_params=[],
                recommended_params=["target_line", "normally_open"],
                notes=["可映射为 OpenDSS 线路开合状态"],
            ),
            TopologyCatalogItem(
                type=NodeType.BREAKER.value,
                label="断路器",
                required_params=[],
                recommended_params=["target_line", "rated_current_a"],
                notes=["用于保护/开断设备表达"],
            ),
            TopologyCatalogItem(
                type=NodeType.FUSE.value,
                label="熔断器",
                required_params=[],
                recommended_params=["target_line", "rated_current_a"],
                notes=["用于熔断器保护设备表达"],
            ),
            TopologyCatalogItem(
                type=NodeType.REGULATOR.value,
                label="电压调节",
                required_params=[],
                recommended_params=["target_transformer", "vreg", "band", "ptratio"],
                notes=["用于后续 RegControl 调压建模"],
            ),
            TopologyCatalogItem(
                type=NodeType.CAPACITOR.value,
                label="电容器",
                required_params=["kvar", "voltage_level_kv"],
                recommended_params=["connection"],
                notes=["用于无功补偿和电压支撑"],
            ),
            TopologyCatalogItem(
                type=NodeType.LOAD.value,
                label="负荷节点",
                required_params=["node_id", "category", "optimize_storage"],
                recommended_params=[
                    "power_factor",
                    "allow_grid_export",
                    "transformer_capacity_kva",
                    "transformer_reserve_ratio",
                ],
                notes=["每个负荷节点后续需要绑定两份 runtime 文件"],
            ),
            TopologyCatalogItem(
                type=NodeType.PV.value,
                label="光伏",
                required_params=["pmpp_kw", "voltage_level_kv"],
                recommended_params=["kva", "pf"],
                notes=["作为独立分布式资源接入，不放在负荷属性中"],
            ),
            TopologyCatalogItem(
                type=NodeType.WIND.value,
                label="风机",
                required_params=["rated_kw", "voltage_level_kv"],
                recommended_params=["pf"],
                notes=["作为独立分布式资源接入"],
            ),
            TopologyCatalogItem(
                type=NodeType.STORAGE.value,
                label="储能",
                required_params=["rated_kw", "rated_kwh", "voltage_level_kv"],
                recommended_params=["initial_soc_pct", "reserve_soc_pct"],
                notes=["映射为 OpenDSS 原生 Storage 元件"],
            ),
            TopologyCatalogItem(
                type=NodeType.STORAGE_ACCESS.value,
                label="储能接入点",
                required_params=[],
                recommended_params=["access_mode", "shared_with_load_node_id"],
                notes=["第二阶段先保留对象定义，后续用于储能独立接入表达"],
            ),
        ]

    def get_edge_catalog(self) -> List[TopologyCatalogItem]:
        common_params = ["length_km", "r_ohm_per_km", "x_ohm_per_km"]
        return [
            TopologyCatalogItem(
                type=EdgeType.LINE.value,
                label="常规连接线",
                required_params=common_params,
                recommended_params=["ampacity", "line_code"],
                notes=["适用于一般 10kV 主干线、分支线或普通连接线"],
            ),
            TopologyCatalogItem(
                type=EdgeType.SPECIAL_LINE.value,
                label="重点接入线",
                required_params=common_params,
                recommended_params=["ampacity", "line_code"],
                notes=["适用于主变至大用户、用户低压接入线等重点线路建模"],
            ),
            TopologyCatalogItem(
                type=EdgeType.FEEDER.value,
                label="主干馈线",
                required_params=common_params,
                recommended_params=["ampacity", "feeder_name"],
                notes=["适用于从母线引出的主干馈线"],
            ),
        ]
