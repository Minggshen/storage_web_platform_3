from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict
import re


_SOURCE_BUS_PATTERN = re.compile(r"^[nN](\d+)$")


def _parse_source_bus_index(source_bus_name: str) -> int:
    """
    由 source_bus_name（如 n0）解析出 0-based 母线编号。
    """
    name = str(source_bus_name).strip()
    match = _SOURCE_BUS_PATTERN.fullmatch(name)
    if match is None:
        raise ValueError("source_bus_name 格式错误。当前仅支持类似 'n0'、'n1' 这种命名。")
    return int(match.group(1))


@dataclass(frozen=True)
class NetworkConfig:
    """
    OpenDSS 网络骨架配置。

    严格口径：
    1. 本模块只负责描述网络骨架与 dss 文件路径；
    2. 不再包含任何默认负荷参数；
    3. 负荷必须由 runtime 表逐日逐时生成到 Loads_Runtime.dss；
    4. 不允许在配置层使用默认 Q/P、默认相数、默认接线方式去兜底构造负荷。
    """

    bus_count: int
    load_node_count: int
    slack_bus: int

    base_mva: float
    base_kv: float

    voltage_min_pu: float
    voltage_max_pu: float

    master_dss_path: str
    runtime_loads_dss_path: str
    storage_case_dss_path: str
    tielines_dss_path: str
    topology_case_dss_path: str
    lines_main_dss_path: str

    source_bus_name: str = "n0"
    source_bus_index: int = 0
    source_bus_base_voltage_v: float = 5773.5
    solve_mode: str = "snap"

    def __post_init__(self) -> None:
        if self.bus_count <= 0:
            raise ValueError("bus_count 必须大于 0。")
        if self.load_node_count <= 0:
            raise ValueError("load_node_count 必须大于 0。")
        if self.load_node_count >= self.bus_count:
            raise ValueError("load_node_count 应小于 bus_count（源点不应计入负荷节点数）。")

        if self.slack_bus < 1 or self.slack_bus > self.bus_count:
            raise ValueError("slack_bus 超出 bus_count 范围。")

        if self.base_mva <= 0:
            raise ValueError("base_mva 必须大于 0。")
        if self.base_kv <= 0:
            raise ValueError("base_kv 必须大于 0。")

        if not (0 < self.voltage_min_pu < self.voltage_max_pu):
            raise ValueError("电压上下限设置错误。")

        if not str(self.source_bus_name).strip():
            raise ValueError("source_bus_name 不能为空。")

        parsed_source_index = _parse_source_bus_index(self.source_bus_name)
        if self.source_bus_index < 0 or self.source_bus_index >= self.bus_count:
            raise ValueError("source_bus_index 超出 bus_count 范围。")
        if parsed_source_index != int(self.source_bus_index):
            raise ValueError(
                f"source_bus_name={self.source_bus_name!r} 与 "
                f"source_bus_index={self.source_bus_index} 不一致。"
            )

        expected_slack_bus = int(self.source_bus_index) + 1
        if int(self.slack_bus) != expected_slack_bus:
            raise ValueError(
                f"slack_bus 与 source_bus_index 不一致："
                f"当前 source_bus_index={self.source_bus_index}，"
                f"则 slack_bus 应为 {expected_slack_bus}。"
            )

        if self.source_bus_base_voltage_v <= 0:
            raise ValueError("source_bus_base_voltage_v 必须大于 0。")

        if not str(self.solve_mode).strip():
            raise ValueError("solve_mode 不能为空。")

        for field_name in (
            "master_dss_path",
            "runtime_loads_dss_path",
            "storage_case_dss_path",
            "tielines_dss_path",
            "topology_case_dss_path",
            "lines_main_dss_path",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} 不能为空。")

    @property
    def source_bus_ordinal_1based(self) -> int:
        """
        源点母线的 1-based 序号，兼容 slack_bus 口径。
        """
        return int(self.source_bus_index) + 1

    @property
    def source_bus_base_voltage_kv(self) -> float:
        return float(self.source_bus_base_voltage_v) / 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_flat_dict(self) -> Dict[str, Any]:
        return {
            "solver": "opendss",
            "bus_count": self.bus_count,
            "load_node_count": self.load_node_count,
            "slack_bus": self.slack_bus,
            "source_bus_index": self.source_bus_index,
            "source_bus_name": self.source_bus_name,
            "base_mva": self.base_mva,
            "base_kv": self.base_kv,
            "voltage_min_pu": self.voltage_min_pu,
            "voltage_max_pu": self.voltage_max_pu,
            "master_dss_path": self.master_dss_path,
            "runtime_loads_dss_path": self.runtime_loads_dss_path,
            "storage_case_dss_path": self.storage_case_dss_path,
            "tielines_dss_path": self.tielines_dss_path,
            "topology_case_dss_path": self.topology_case_dss_path,
            "lines_main_dss_path": self.lines_main_dss_path,
            "source_bus_base_voltage_v": self.source_bus_base_voltage_v,
            "solve_mode": self.solve_mode,
        }

    def resolve_master_dss_path(self, project_root: Path | None = None) -> Path:
        return resolve_path(self.master_dss_path, project_root=project_root)

    def resolve_runtime_loads_dss_path(self, project_root: Path | None = None) -> Path:
        return resolve_path(self.runtime_loads_dss_path, project_root=project_root)

    def resolve_storage_case_dss_path(self, project_root: Path | None = None) -> Path:
        return resolve_path(self.storage_case_dss_path, project_root=project_root)

    def resolve_tielines_dss_path(self, project_root: Path | None = None) -> Path:
        return resolve_path(self.tielines_dss_path, project_root=project_root)

    def resolve_topology_case_dss_path(self, project_root: Path | None = None) -> Path:
        return resolve_path(self.topology_case_dss_path, project_root=project_root)

    def resolve_lines_main_dss_path(self, project_root: Path | None = None) -> Path:
        return resolve_path(self.lines_main_dss_path, project_root=project_root)


def resolve_path(path_like: str | Path, project_root: Path | None = None) -> Path:
    path = Path(str(path_like))
    if path.is_absolute():
        return path.resolve()

    if project_root is not None:
        return (project_root / path).resolve()

    return path.resolve()


def get_default_network_config(
    project_root: Path | None = None,
    load_node_count: int | None = None,
    bus_count: int | None = None,
) -> NetworkConfig:
    """
    返回默认 OpenDSS 网络配置。

    目录约定：
    project_root/
        inputs/
            dss/
                ieee33/
                    Master.dss
                    Loads_Runtime.dss
                    Storage_Case.dss
                    TieLines.dss
                    Topology_Case.dss
                    Lines_Main.dss
    """
    base = project_root if project_root is not None else Path(".")
    dss_dir = base / "inputs" / "dss" / "ieee33"

    load_node_count_final = int(load_node_count) if load_node_count is not None else 33
    bus_count_final = int(bus_count) if bus_count is not None else (load_node_count_final + 1)

    if load_node_count_final <= 0:
        raise ValueError("load_node_count 必须大于 0。")
    if bus_count_final <= load_node_count_final:
        raise ValueError(
            f"bus_count 必须大于 load_node_count。当前 bus_count={bus_count_final}，load_node_count={load_node_count_final}。"
        )

    return NetworkConfig(
        bus_count=bus_count_final,
        load_node_count=load_node_count_final,
        slack_bus=1,           # 对应 n0

        base_mva=100.0,
        base_kv=10.0,

        voltage_min_pu=0.95,
        voltage_max_pu=1.05,

        master_dss_path=str(dss_dir / "Master.dss"),
        runtime_loads_dss_path=str(dss_dir / "Loads_Runtime.dss"),
        storage_case_dss_path=str(dss_dir / "Storage_Case.dss"),
        tielines_dss_path=str(dss_dir / "TieLines.dss"),
        topology_case_dss_path=str(dss_dir / "Topology_Case.dss"),
        lines_main_dss_path=str(dss_dir / "Lines_Main.dss"),

        source_bus_name="n0",
        source_bus_index=0,
        source_bus_base_voltage_v=5773.5,
        solve_mode="snap",
    )