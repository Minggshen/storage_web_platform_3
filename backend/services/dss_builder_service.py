from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DssBuildArtifact:
    relative_path: str
    absolute_path: str
    exists: bool = True


class DssBuilderService:
    """
    Compile frontend visual topology into a minimal OpenDSS input set.

    This version intentionally keeps the modelling assumptions simple:
    - balanced three-phase equivalent
    - main and optional customer distribution transformers
    - lines as Line elements
    - loads as Load elements
    - optional PVSystem, Generator, Storage, Capacitor and protection/control objects
    """

    SERVICE_LINE_LINECODE = "LC_CABLE"
    SERVICE_LINE_DEFAULT_LENGTH_KM = 0.005
    SERVICE_LINE_RESOURCE_MARGIN = 1.1
    SERVICE_LINE_EMERGENCY_MARGIN = 1.2
    SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN = 1.25
    SERVICE_LINE_MIN_RATED_A = 1.0
    # For 0.4 kV service connections with very high current (>1500 A), a single cable's
    # R1=0.254 ohm/km gives unrealistic voltage drop. Real installations use parallel
    # cables or busbars, giving effective Z << single-cable Z. Use OpenDSS WireData
    # parallel-cable formula: Rac_eq = Rac_single / n,  X_eq = X_single / n.
    SERVICE_LINE_LOW_Z_CURRENT_THRESHOLD_A = 1500.0

    # OpenDSS 8500Bus/WireData.dss — 铜缆电气参数（50 Hz，ohm/km）
    # 用于接户线并联等效阻抗计算。来源：OpenDSS 官方测试工程。
    WIRE_DATA_CU: dict[str, dict[str, float]] = {
        # name, Rac_ohm_per_km, GMR_cm, Radius_cm, NormAmps, EmergAmps
        "250_CU":   {"rac": 0.159692, "gmr": 0.551688, "radius": 0.72898,  "normamps": 540,  "emergamps": 540},
        "350_CU":   {"rac": 0.114643, "gmr": 0.652780, "radius": 0.90170,  "normamps": 660,  "emergamps": 660},
        "400_CU":   {"rac": 0.100662, "gmr": 0.697738, "radius": 0.92202,  "normamps": 730,  "emergamps": 730},
        "500_CU":   {"rac": 0.080778, "gmr": 0.792734, "radius": 1.03378,  "normamps": 840,  "emergamps": 840},
        "600_CU":   {"rac": 0.062323, "gmr": 0.838200, "radius": 1.09982,  "normamps": 900,  "emergamps": 900},
        "750_CU":   {"rac": 0.055302, "gmr": 0.971804, "radius": 1.26619,  "normamps": 1090, "emergamps": 1090},
        "1000_CU":  {"rac": 0.042875, "gmr": 1.121921, "radius": 1.46177,  "normamps": 1300, "emergamps": 1300},
    }
    # X/R 比（50 Hz 铜缆典型值），用于估算并联后的 X1
    WIRE_XR_RATIO: float = 0.46

    LINE_CODES: dict[str, dict[str, float]] = {
        "LC_MAIN": {
            "r1": 0.251742424,
            "x1": 0.255208333,
            "r0": 0.251742424,
            "x0": 0.255208333,
            "c1": 2.270366128,
            "c0": 2.270366128,
            "normamps": 1200.0,
            "emergamps": 1500.0,
        },
        "LC_BRANCH": {
            "r1": 0.363958000,
            "x1": 0.269167000,
            "r0": 0.363958000,
            "x0": 0.269167000,
            "c1": 2.192200000,
            "c0": 2.192200000,
            "normamps": 800.0,
            "emergamps": 1000.0,
        },
        "LC_CABLE": {
            "r1": 0.254261364,
            "x1": 0.097045455,
            "r0": 0.254261364,
            "x0": 0.097045455,
            "c1": 44.706615220,
            "c0": 44.706615220,
            "normamps": 1400.0,
            "emergamps": 1700.0,
        },
        "LC_LIGHT": {
            "r1": 0.530208000,
            "x1": 0.281345000,
            "r0": 0.530208000,
            "x0": 0.281345000,
            "c1": 2.122570000,
            "c0": 2.122570000,
            "normamps": 300.0,
            "emergamps": 450.0,
        },
    }

    def __init__(self, base_kv: float = 10.0) -> None:
        self.base_kv = float(base_kv)

    def compile_topology(
        self,
        project_id: str,
        topology: dict[str, Any],
        output_dir: str | Path,
    ) -> dict[str, Any]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        nodes = list(topology.get("nodes", []) or [])
        edges = list(topology.get("edges", []) or [])

        node_map = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
        phase_count = self._topology_phases(nodes, edges)
        source_node = next((node for node in nodes if self._is_grid_node(node)), None)

        bus_map = self._build_bus_map(nodes)
        linecodes_text = self._build_linecodes()
        transformers_text = self._build_transformers(nodes, edges, node_map)
        lines_text = self._build_lines(edges, node_map)
        loads_text = self._build_loads(nodes)
        distributed_text = self._build_distributed_resources(nodes)
        capacitors_text = self._build_capacitors(nodes)
        controls_text = self._build_controls(nodes)
        protection_text = self._build_protection_case(nodes)
        topology_case_text = self._build_topology_case(edges, node_map)
        storage_case_text = self._build_storage_case(nodes)
        tielines_text = self._build_tielines(edges, node_map)
        circuit_text = self._build_circuit(project_id, nodes, edges)
        source_text = self._build_source(nodes)
        master_text = self._build_master(nodes, edges)
        line_summary = self._build_line_summary(edges, node_map)
        topology_case_summary = self._build_topology_case_summary(edges, node_map)
        voltage_bases = self._voltage_bases(nodes, edges)

        files = {
            "Circuit.dss": circuit_text,
            "Source.dss": source_text,
            "LineCodes_Custom.dss": linecodes_text,
            "Transformers.dss": transformers_text,
            "Lines_Main.dss": lines_text,
            "TieLines.dss": tielines_text,
            "Loads_Runtime.dss": loads_text,
            "Distributed_Resources.dss": distributed_text,
            "Capacitors.dss": capacitors_text,
            "Storage_Case.dss": storage_case_text,
            "Controls.dss": controls_text,
            "Protection_Case.dss": protection_text,
            "Topology_Case.dss": topology_case_text,
            "Master.dss": master_text,
        }

        artifacts: list[dict[str, Any]] = []
        for filename, content in files.items():
            file_path = output_path / filename
            file_path.write_text(content, encoding="utf-8")
            artifacts.append(
                DssBuildArtifact(
                    relative_path=filename,
                    absolute_path=str(file_path),
                    exists=True,
                ).__dict__
            )

        warnings = self._build_warnings(nodes, edges, node_map)
        runtime_injection_contract = self._build_runtime_injection_contract(nodes)
        structural_checks = self._build_structural_checks(
            nodes=nodes,
            edges=edges,
            node_map=node_map,
            artifacts=artifacts,
            bus_map=bus_map,
            line_summary=line_summary,
            topology_case_summary=topology_case_summary,
            warnings=warnings,
        )
        summary = {
            "project_id": project_id,
            "base_kv": self.base_kv,
            "voltage_bases": voltage_bases,
            "source_bus": self._bus_name(source_node) if source_node else "sourcebus",
            "phase_count": phase_count,
            "linecode_count": len(self.LINE_CODES),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "grid_count": sum(1 for n in nodes if self._is_grid_node(n)),
            "transformer_count": sum(1 for n in nodes if self._is_transformer_node(n)),
            "load_count": sum(1 for n in nodes if str(n.get("type")) == "load"),
            "pv_count": sum(1 for n in nodes if str(n.get("type")) == "pv"),
            "storage_count": sum(1 for n in nodes if str(n.get("type")) == "storage"),
            "standalone_storage_count": sum(1 for n in nodes if str(n.get("type")) == "storage"),
            "optimizable_load_count": sum(
                1
                for n in nodes
                if str(n.get("type")) == "load" and self._bool(self._params(n).get("optimize_storage"), False)
            ),
            "storage_placeholder_count": sum(
                1
                for n in nodes
                if str(n.get("type")) == "load" and self._bool(self._params(n).get("storage_placeholder"), False)
            ),
            "capacitor_count": sum(1 for n in nodes if str(n.get("type")) == "capacitor"),
            "bus_count": len(bus_map),
            "bus_map": bus_map,
            "line_summary": line_summary,
            "line_count_by_code": self._count_by_key(line_summary, "linecode"),
            "topology_case_summary": topology_case_summary,
            "runtime_injection_contract": runtime_injection_contract,
            "structural_checks": structural_checks,
            "opendss_probe": self._probe_opendss_compile(output_path / "Master.dss"),
            "artifacts": artifacts,
            "warnings": structural_checks["warnings"],
            "errors": structural_checks["errors"],
        }

        bus_map_path = output_path / "bus_map.json"
        bus_map_path.write_text(json.dumps(bus_map, ensure_ascii=False, indent=2), encoding="utf-8")

        summary_path = output_path / "dss_compile_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "dss_dir": str(output_path),
            "dss_master_path": str(output_path / "Master.dss"),
            "dss_master_preview": master_text,
            "dss_files": [a["relative_path"] for a in artifacts] + ["bus_map.json", "dss_compile_summary.json"],
            "dss_compile_summary": summary,
        }

    def _build_circuit(self, project_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
        phases = self._topology_phases(nodes, edges)
        bus_suffix = self._phase_suffix(phases)
        source_node = next((node for node in nodes if self._is_grid_node(node)), None)
        params = self._params(source_node) if source_node else {}
        source_bus = self._bus_name(source_node) if source_node else "sourcebus"
        base_kv = self._source_voltage_kv(source_node, phases)
        pu = self._num(params.get("pu"), 1.0)
        return "\n".join(
            [
                f"! Project {project_id}",
                "Clear",
                "Set DefaultBaseFrequency=50",
                f"New Circuit.VisualModel basekv={base_kv:g} pu={pu:g} phases={phases} bus1={source_bus}{bus_suffix}",
                "",
            ]
        )

    def _build_source(self, nodes: list[dict[str, Any]]) -> str:
        source_node = next((node for node in nodes if self._is_grid_node(node)), None)
        params = self._params(source_node) if source_node else {}
        pu = self._num(params.get("pu"), 1.0)
        phases = self._node_phases(source_node, self._topology_phases(nodes, [])) if source_node else self._topology_phases(nodes, [])
        base_kv = self._source_voltage_kv(source_node, phases)
        source_bus = self._bus_name(source_node) if source_node else "sourcebus"
        mvasc3 = self._num(params.get("mvasc3"), 1000.0)
        mvasc1 = self._num(params.get("mvasc1"), mvasc3)
        x1r1 = self._num(params.get("x1r1"), 10.0)
        x0r0 = self._num(params.get("x0r0"), 3.0)
        return "\n".join(
            [
                "! Source equivalent",
                (
                    f"Edit Vsource.Source bus1={source_bus}{self._phase_suffix(phases)} phases={phases} "
                    f"basekv={base_kv:g} pu={pu:g} angle=0 MVAsc3={mvasc3:g} MVAsc1={mvasc1:g} "
                    f"X1R1={x1r1:g} X0R0={x0r0:g}"
                ),
                "",
            ]
        )

    def _build_linecodes(self) -> str:
        lines = [
            "! Project line code library",
            "! Three-phase sequence parameters are written with OpenDSS LineCode syntax.",
        ]
        for name, values in self.LINE_CODES.items():
            lines.extend(
                [
                    f"New LineCode.{name} nphases=3 BaseFreq=50 Units=km",
                    f"~ R1={values['r1']:.9f} X1={values['x1']:.9f} R0={values['r0']:.9f} X0={values['x0']:.9f}",
                    f"~ C1={values['c1']:.9f} C0={values['c0']:.9f}",
                    "",
                ]
            )
        return "\n".join(lines)

    def _build_transformers(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
    ) -> str:
        lines: list[str] = ["! Transformer elements"]
        source_node = next((node for node in nodes if self._is_grid_node(node)), None)
        source_bus = self._bus_name(source_node) if source_node else "sourcebus"
        for node in nodes:
            if not self._is_transformer_node(node):
                continue
            node_id = self._safe_name(str(node.get("id", "tx")))
            params = self._params(node)
            is_customer_tx = self._is_distribution_transformer_node(node)
            phases = self._node_phases(node, self._topology_phases(nodes, []))
            rated_kva = self._num(params.get("rated_kva"), 1000.0 if is_customer_tx else 31500.0)
            sec_kv = self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), phases)
            pri_kv = self._source_voltage_kv(source_node, phases)
            if params.get("primary_voltage_kv") not in (None, ""):
                pri_kv = self._distribution_voltage_kv_for_opendss(params.get("primary_voltage_kv"), phases)
                if not is_customer_tx:
                    pri_kv = self._source_voltage_kv({"params": {"base_kv": params.get("primary_voltage_kv")}}, phases)
            primary_bus = self._infer_transformer_primary_bus(node, edges, node_map, source_bus)
            bus = self._bus_name(node)
            primary_conn = self._dss_connection(params.get("primary_conn"), "delta" if is_customer_tx else "wye")
            secondary_conn = self._dss_connection(params.get("secondary_conn"), "wye")
            xhl = self._num(params.get("xhl_percent"), self._num(params.get("xhl"), 7.0))
            percent_r = self._num(params.get("percent_r"), self._num(params.get("r_percent"), 0.5))
            tap = self._num(params.get("tap"), 1.0)
            imag = self._num(params.get("imag_percent"), 0.0)
            noloadloss = self._num(params.get("noloadloss_percent"), 0.0)
            lines.extend(
                [
                    (
                        f"New Transformer.{node_id} phases={phases} windings=2 xhl={xhl:g} "
                        f"%imag={imag:g} %noloadloss={noloadloss:g}"
                    ),
                    (
                        f"~ wdg=1 bus={primary_bus}{self._phase_suffix(phases)} conn={primary_conn} "
                        f"kv={pri_kv:g} kva={rated_kva:g} %r={percent_r:g}"
                    ),
                    (
                        f"~ wdg=2 bus={bus}{self._phase_suffix(phases)} conn={secondary_conn} "
                        f"kv={sec_kv:g} kva={rated_kva:g} %r={percent_r:g} tap={tap:g}"
                    ),
                    "",
                ]
            )
        if len(lines) == 1:
            lines.append("! no transformer nodes found")
        return "\n".join(lines)

    def _build_lines(self, edges: list[dict[str, Any]], node_map: dict[str, dict[str, Any]]) -> str:
        lines: list[str] = ["! Line elements"]
        for edge in edges:
            edge_id = self._safe_name(str(edge.get("id", "line")))
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                lines.append(f"! skipped {edge_id}: invalid endpoint")
                continue

            from_node = node_map[from_node_id]
            to_node = node_map[to_node_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                lines.append(f"! skipped {edge_id}: connection is represented by Transformer winding")
                continue

            from_bus = self._bus_name(from_node)
            to_bus = self._bus_name(to_node)
            phases = self._edge_phases(edge, from_node, to_node)
            service_profile = self._distribution_service_edge_profile(edge, from_node, to_node)

            length_km = self._num(params.get("length_km"), service_profile["default_length_km"] if service_profile else 1.0)

            # Determine if this service edge uses explicit parallel-cable impedance
            use_explicit_z = (
                service_profile
                and service_profile.get("linecode") == ""
                and all(k in service_profile for k in ("r1", "x1"))
            )

            if use_explicit_z:
                # High-current 0.4 kV service: use explicit r1/x1 from parallel-cable formula
                # (OpenDSS 8500Bus/WireData.dss parallel-cable equivalent)
                r1 = float(service_profile["r1"])
                x1 = float(service_profile["x1"])
                r0 = float(service_profile["r0"])
                x0 = float(service_profile["x0"])
                c1 = float(service_profile.get("c1", 0.0))
                c0 = float(service_profile.get("c0", 0.0))
                cable_name = service_profile.get("cable_name", "")
                cable_parallel = int(service_profile.get("cable_parallel", 1))
                electrical = f"r1={r1:.9f} x1={x1:.9f} r0={r0:.9f} x0={x0:.9f} c1={c1:.6f} c0={c0:.6f}"
                normamps = float(service_profile["normamps"])
                emergamps = float(service_profile["emergamps"])
                enabled = "yes" if self._bool(params.get("enabled"), True) and not self._bool(params.get("normally_open"), False) else "no"
                lines.append(
                    f"New Line.{edge_id} phases={phases} bus1={from_bus}{self._phase_suffix(phases)} bus2={to_bus}{self._phase_suffix(phases)} "
                    f"length={length_km:g} units=km {electrical} normamps={normamps:g} emergamps={emergamps:g} enabled={enabled}"
                    + (f" ! {cable_name} x{cable_parallel}" if cable_name else "")
                )
                continue

            linecode = str(
                params.get("linecode")
                or params.get("line_code")
                or (service_profile["linecode"] if service_profile else "LC_MAIN")
            ).strip()
            defaults = self.LINE_CODES.get(linecode, self.LINE_CODES["LC_MAIN"])
            r_ohm_per_km = self._num(params.get("r_ohm_per_km"), defaults["r1"])
            x_ohm_per_km = self._num(params.get("x_ohm_per_km"), defaults["x1"])
            if service_profile:
                normamps = float(service_profile["normamps"])
                emergamps = float(service_profile["emergamps"])
            else:
                normamps = self._num(params.get("rated_current_a"), defaults["normamps"])
                emergamps = self._num(params.get("emerg_current_a"), defaults["emergamps"])
            enabled = "yes" if self._bool(params.get("enabled"), True) and not self._bool(params.get("normally_open"), False) else "no"

            if linecode in self.LINE_CODES:
                electrical = f"linecode={linecode}"
            else:
                r0 = self._num(params.get("r0_ohm_per_km"), r_ohm_per_km)
                x0 = self._num(params.get("x0_ohm_per_km"), x_ohm_per_km)
                c1 = self._num(params.get("c1_nf_per_km"), 0.0)
                c0 = self._num(params.get("c0_nf_per_km"), 0.0)
                electrical = f"r1={r_ohm_per_km:g} x1={x_ohm_per_km:g} r0={r0:g} x0={x0:g} c1={c1:g} c0={c0:g}"

            lines.append(
                f"New Line.{edge_id} phases={phases} bus1={from_bus}{self._phase_suffix(phases)} bus2={to_bus}{self._phase_suffix(phases)} "
                f"length={length_km:g} units=km {electrical} normamps={normamps:g} emergamps={emergamps:g} enabled={enabled}"
            )
        if len(lines) == 1:
            lines.append("! no line edges found")
        return "\n".join(lines)

    def _build_loads(self, nodes: list[dict[str, Any]]) -> str:
        lines: list[str] = ["! Load elements"]
        for node in nodes:
            if str(node.get("type")) != "load":
                continue
            node_id = self._safe_name(str(node.get("id", "load")))
            params = self._params(node)
            load_name = self._load_name(node)
            phases = self._node_phases(node, self._topology_phases(nodes, []))
            kv = self._load_voltage_kv_for_opendss(params, phases)
            kw = self._num(params.get("design_kw"), 0.0)
            pf = self._num(params.get("pf"), 0.95)
            model = int(self._num(params.get("model"), 1))
            conn = str(params.get("connection", "wye"))
            bus = self._bus_name(node)
            kvar = self._num(params.get("kvar"), kw * self._num(params.get("q_to_p_ratio"), 0.25))
            load_power = f"kw={kw:g} kvar={kvar:g}" if "kvar" in params or "q_to_p_ratio" in params else f"kw={kw:g} pf={pf:g}"
            lines.append(
                f"New Load.{load_name or node_id} bus1={bus}{self._phase_suffix(phases)} phases={phases} conn={conn} kv={kv:g} {load_power} Model={model} Status=variable"
            )
        if len(lines) == 1:
            lines.append("! no load nodes found")
        return "\n".join(lines)

    def _build_distributed_resources(self, nodes: list[dict[str, Any]]) -> str:
        lines: list[str] = ["! Distributed resource elements"]
        for node in nodes:
            node_type = str(node.get("type"))
            if node_type not in {"pv", "wind"}:
                continue
            params = self._params(node)
            if not self._bool(params.get("enabled"), True):
                continue
            name = self._safe_name(str(params.get("dss_name") or node.get("id") or node_type))
            phases = self._node_phases(node, self._topology_phases(nodes, []))
            bus = self._bus_name(node)
            kv = self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), phases)
            pf = self._num(params.get("pf"), 1.0 if node_type == "pv" else 0.98)
            if node_type == "pv":
                pmpp = self._num(params.get("pmpp_kw"), self._num(params.get("rated_kw"), 100.0))
                kva = self._num(params.get("kva"), pmpp)
                irradiance = self._num(params.get("irradiance"), 1.0)
                lines.append(
                    f"New PVSystem.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} kV={kv:g} kVA={kva:g} Pmpp={pmpp:g} pf={pf:g} irradiance={irradiance:g}"
                )
            else:
                kw = self._num(params.get("rated_kw"), 100.0)
                model = int(self._num(params.get("model"), 1))
                lines.append(
                    f"New Generator.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} kV={kv:g} kW={kw:g} pf={pf:g} model={model}"
                )
        if len(lines) == 1:
            lines.append("! no PVSystem or Generator nodes")
        return "\n".join(lines)

    def _build_capacitors(self, nodes: list[dict[str, Any]]) -> str:
        lines: list[str] = ["! Capacitor elements"]
        for node in nodes:
            if str(node.get("type")) != "capacitor":
                continue
            params = self._params(node)
            if not self._bool(params.get("enabled"), True):
                continue
            name = self._safe_name(str(params.get("dss_name") or node.get("id") or "capacitor"))
            phases = self._node_phases(node, self._topology_phases(nodes, []))
            bus = self._bus_name(node)
            kv = self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), phases)
            kvar = self._num(params.get("kvar"), 300.0)
            conn = self._dss_connection(params.get("connection"), "wye")
            lines.append(
                f"New Capacitor.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} kV={kv:g} kvar={kvar:g} conn={conn}"
            )
        if len(lines) == 1:
            lines.append("! no capacitor nodes")
        return "\n".join(lines)

    def _build_controls(self, nodes: list[dict[str, Any]]) -> str:
        lines: list[str] = ["! Voltage regulation controls"]
        for node in nodes:
            if str(node.get("type")) != "regulator":
                continue
            params = self._params(node)
            if not self._bool(params.get("enabled"), True):
                continue
            raw_transformer = str(params.get("target_transformer") or params.get("transformer_name") or "").strip()
            name = self._safe_name(str(params.get("dss_name") or node.get("id") or "reg"))
            if not raw_transformer:
                lines.append(f"! regulator {name} skipped: target_transformer is empty")
                continue
            transformer = self._safe_name(raw_transformer)
            winding = int(self._num(params.get("winding"), 2))
            vreg = self._num(params.get("vreg"), 120.0)
            band = self._num(params.get("band"), 2.0)
            ptratio = self._num(params.get("ptratio"), 60.0)
            lines.append(
                f"New RegControl.{name} transformer={transformer} winding={winding} vreg={vreg:g} band={band:g} ptratio={ptratio:g} enabled=yes"
            )
        if len(lines) == 1:
            lines.append("! no regulator nodes")
        return "\n".join(lines)

    def _build_protection_case(self, nodes: list[dict[str, Any]]) -> str:
        lines: list[str] = ["! Switching and protection devices"]
        for node in nodes:
            node_type = str(node.get("type"))
            if node_type not in {"switch", "breaker", "fuse"}:
                continue
            params = self._params(node)
            name = self._safe_name(str(params.get("dss_name") or node.get("id") or node_type))
            raw_target_line = str(params.get("target_line") or params.get("monitored_line") or "").strip()
            enabled = "yes" if self._bool(params.get("enabled"), True) and not self._bool(params.get("normally_open"), False) else "no"
            if not raw_target_line:
                lines.append(f"! {node_type} {name} skipped: target_line is empty")
                continue
            target_line = self._safe_name(raw_target_line)
            if node_type == "switch":
                lines.append(f"Edit Line.{target_line} switch=yes enabled={enabled}")
            elif node_type == "breaker":
                lines.append(
                    f"New Recloser.{name} MonitoredObj=Line.{target_line} MonitoredTerm=1 SwitchedObj=Line.{target_line} SwitchedTerm=1 Shots=1 NumFast=1 enabled={enabled}"
                )
            else:
                rated_current = self._num(params.get("rated_current_a"), 200.0)
                lines.append(
                    f"New Fuse.{name} MonitoredObj=Line.{target_line} MonitoredTerm=1 SwitchedObj=Line.{target_line} SwitchedTerm=1 RatedCurrent={rated_current:g} enabled={enabled}"
                )
        if len(lines) == 1:
            lines.append("! no switch/protection nodes")
        return "\n".join(lines)

    def _build_topology_case(self, edges: list[dict[str, Any]], node_map: dict[str, dict[str, Any]]) -> str:
        lines = ["! Line enablement generated from visual topology"]
        for edge in edges:
            edge_id = self._safe_name(str(edge.get("id", "line")))
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                lines.append(f"! skipped {edge_id}: invalid endpoint")
                continue
            from_node = node_map[from_node_id]
            to_node = node_map[to_node_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                lines.append(f"! skipped {edge_id}: connection is represented by Transformer winding")
                continue
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            enabled = "yes" if self._bool(params.get("enabled"), True) and not self._bool(params.get("normally_open"), False) else "no"
            lines.append(f"Edit Line.{edge_id} enabled={enabled}")
        if len(lines) == 1:
            lines.append("! no switchable lines")
        return "\n".join(lines)

    def _build_tielines(self, edges: list[dict[str, Any]], node_map: dict[str, dict[str, Any]]) -> str:
        tie_count = 0
        lines = ["! Tie-line declarations are kept in Lines_Main.dss; this file documents normally-open lines."]
        for edge in edges:
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            if not self._bool(params.get("normally_open"), False):
                continue
            if str(edge.get("from_node_id", "")).strip() not in node_map or str(edge.get("to_node_id", "")).strip() not in node_map:
                continue
            tie_count += 1
            lines.append(f"! normally open: Line.{self._safe_name(str(edge.get('id', 'line')))}")
        if tie_count == 0:
            lines.append("! no tie-lines")
        return "\n".join(lines)

    def _build_storage_case(self, nodes: list[dict[str, Any]]) -> str:
        lines = [
            "! Standalone storage nodes are exported here; optimization target storage is still injected by the evaluation workflow.",
            "! Set load node dss_bus_name/dss_load_name so OpenDSS full-recheck can target the right bus.",
        ]
        for node in nodes:
            if str(node.get("type")) == "storage":
                params = self._params(node)
                if not self._bool(params.get("enabled"), True):
                    continue
                phases = self._node_phases(node, self._topology_phases(nodes, []))
                bus = self._bus_name(node)
                kv = self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), phases)
                power = self._num(params.get("rated_kw"), 100.0)
                energy = self._num(params.get("rated_kwh"), max(power, 1.0) * 2.0)
                reserve = self._num(params.get("reserve_soc_pct"), 10.0)
                stored = self._num(params.get("initial_soc_pct"), 50.0)
                name = self._safe_name(str(params.get("dss_name") or node.get("id") or "storage"))
                lines.extend(
                    [
                        f"New Storage.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} conn=wye kV={kv:g}",
                        f"~ kWrated={power:g} kWhrated={energy:g} kVA={power:g}",
                        f"~ kW=0 kvar=0 %stored={stored:g} %reserve={reserve:g} state=idling dispmode=external",
                    ]
                )
                continue
            if str(node.get("type")) != "load":
                continue
            params = self._params(node)
            if not self._bool(params.get("storage_placeholder"), False):
                continue
            phases = self._node_phases(node, self._topology_phases(nodes, []))
            bus = self._bus_name(node)
            kv = self._load_voltage_kv_for_opendss(params, phases)
            power = self._num(params.get("storage_placeholder_kw"), 1.0)
            energy = self._num(params.get("storage_placeholder_kwh"), max(power, 1.0) * 2.0)
            name = self._safe_name(str(params.get("storage_name") or f"ES_{node.get('id', 'load')}"))
            lines.extend(
                [
                    f"New Storage.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} conn=wye kV={kv:g}",
                    f"~ kWrated={power:g} kWhrated={energy:g} kVA={power:g}",
                    "~ kW=0 kvar=0 %stored=50 %reserve=10 state=idling dispmode=external",
                ]
            )
        return "\n".join(lines)

    def _build_master(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
        voltage_bases = ", ".join(f"{value:g}" for value in self._voltage_bases(nodes, edges))
        has_enabled_controls = any(
            str(node.get("type")) == "regulator"
            and self._bool(self._params(node).get("enabled"), True)
            and str(self._params(node).get("target_transformer") or self._params(node).get("transformer_name") or "").strip()
            for node in nodes
        )
        control_mode = "STATIC" if has_enabled_controls else "OFF"
        return "\n".join(
            [
                "Redirect Circuit.dss",
                "Redirect Source.dss",
                "Redirect Transformers.dss",
                "Redirect LineCodes_Custom.dss",
                "Redirect Lines_Main.dss",
                "Redirect TieLines.dss",
                "Redirect Loads_Runtime.dss",
                "Redirect Distributed_Resources.dss",
                "Redirect Capacitors.dss",
                "Redirect Storage_Case.dss",
                "Redirect Controls.dss",
                "Redirect Topology_Case.dss",
                "Redirect Protection_Case.dss",
                "",
                f"Set VoltageBases=[{voltage_bases}]",
                "CalcVoltageBases",
                "Set Mode=Snapshot",
                f"Set ControlMode={control_mode}",
                "Set MaxIterations=50",
                "Set Tolerance=0.00001",
                "Solve",
                "",
            ]
        )

    def _build_warnings(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
    ) -> list[str]:
        warnings: list[str] = []
        if not any(self._is_transformer_node(n) for n in nodes):
            warnings.append("未检测到主变节点，DSS 仅能生成占位电路。")
        if not any(str(n.get("type")) == "load" for n in nodes):
            warnings.append("未检测到负荷节点。")
        for edge in edges:
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                warnings.append(f"线路 {edge.get('id', '')} 存在非法端点。")
        return warnings

    def _build_bus_map(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            str(node.get("id")): {
                "node_id": str(node.get("id")),
                "node_name": str(node.get("name") or node.get("id")),
                "node_type": str(node.get("type")),
                "bus": self._bus_name(node),
                "load": self._load_name(node) if str(node.get("type")) == "load" else None,
                "voltage_level_kv": self._node_voltage_kv(node),
                "phases": self._node_phases(node, 3),
            }
            for node in nodes
            if node.get("id") is not None
        }

    def _build_line_summary(self, edges: list[dict[str, Any]], node_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        capacity_index = self._build_line_capacity_index(edges, node_map)
        for edge in edges:
            edge_id = self._safe_name(str(edge.get("id", "line")))
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                continue
            from_node = node_map[from_node_id]
            to_node = node_map[to_node_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                continue

            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            phases = self._edge_phases(edge, from_node, to_node)
            service_profile = self._distribution_service_edge_profile(edge, from_node, to_node)
            linecode = str(
                params.get("linecode")
                or params.get("line_code")
                or (service_profile["linecode"] if service_profile else "LC_MAIN")
            ).strip()
            defaults = self.LINE_CODES.get(linecode, self.LINE_CODES["LC_MAIN"])
            if service_profile:
                normamps = float(service_profile["normamps"])
                emergamps = float(service_profile["emergamps"])
            else:
                normamps = self._num(params.get("rated_current_a"), defaults["normamps"])
                emergamps = self._num(params.get("emerg_current_a"), defaults["emergamps"])
            enabled = self._bool(params.get("enabled"), True) and not self._bool(params.get("normally_open"), False)
            row = {
                "id": edge_id,
                "name": str(edge.get("name") or edge.get("id") or ""),
                "type": str(edge.get("type") or "line"),
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "from_bus": self._bus_name(from_node),
                "to_bus": self._bus_name(to_node),
                "phases": phases,
                "length_km": self._num(params.get("length_km"), service_profile["default_length_km"] if service_profile else 1.0),
                "linecode": linecode,
                "normamps": normamps,
                "emergamps": emergamps,
                "enabled": enabled,
                "normally_open": self._bool(params.get("normally_open"), False),
                "auto_service_line": bool(service_profile),
                "service_secondary_kv": float(service_profile["secondary_kv"]) if service_profile else None,
                "service_transformer_kva": float(service_profile["transformer_kva"]) if service_profile else None,
                "service_resource_kva": float(service_profile["resource_kva"]) if service_profile else None,
                "service_transformer_current_a": float(service_profile["transformer_current_a"]) if service_profile else None,
                "service_resource_current_a": float(service_profile["resource_current_a"]) if service_profile else None,
                "service_equivalent_mode": service_profile.get("equivalent_mode") if service_profile else None,
                "service_cable_name": service_profile.get("cable_name") if service_profile else None,
                "service_cable_parallel": service_profile.get("cable_parallel") if service_profile else None,
                "service_equivalent_r1_ohm_per_km": service_profile.get("r1") if service_profile else None,
                "service_equivalent_x1_ohm_per_km": service_profile.get("x1") if service_profile else None,
                "service_parallel_note": service_profile.get("parallel_note") if service_profile else None,
            }
            row.update(capacity_index.get(edge_id, {}))
            summary.append(row)
        return summary

    def _build_line_capacity_index(
        self,
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        outgoing: dict[str, list[str]] = {}
        for edge in edges:
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                continue
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            if not self._bool(params.get("enabled"), True) or self._bool(params.get("normally_open"), False):
                continue
            outgoing.setdefault(from_node_id, []).append(to_node_id)

        def downstream_ids(start_id: str) -> set[str]:
            seen: set[str] = set()
            stack = [start_id]
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                stack.extend(next_id for next_id in outgoing.get(current, []) if next_id not in seen)
            return seen

        index: dict[str, dict[str, Any]] = {}
        for edge in edges:
            edge_id = self._safe_name(str(edge.get("id", "line")))
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                continue
            from_node = node_map[from_node_id]
            to_node = node_map[to_node_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                continue

            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            service_profile = self._distribution_service_edge_profile(edge, from_node, to_node)
            linecode = str(
                params.get("linecode")
                or params.get("line_code")
                or (service_profile["linecode"] if service_profile else "LC_MAIN")
            ).strip()
            defaults = self.LINE_CODES.get(linecode, self.LINE_CODES["LC_MAIN"])
            normamps = (
                float(service_profile["normamps"])
                if service_profile
                else self._num(params.get("rated_current_a"), defaults["normamps"])
            )

            reached = downstream_ids(to_node_id)
            downstream_transformer_kva = 0.0
            downstream_load_kva = 0.0
            for node_id in reached:
                node = node_map.get(node_id)
                if not node:
                    continue
                if self._is_distribution_transformer_node(node):
                    downstream_transformer_kva += self._num(self._params(node).get("rated_kva"), 0.0)
                if str(node.get("type")).strip().lower() == "load":
                    downstream_load_kva += self._resource_apparent_power_kva(node)

            apparent_kva = max(downstream_transformer_kva, downstream_load_kva)
            voltage_kv = self._edge_voltage_kv(edge, from_node, to_node)
            required_current_a = self._three_phase_current_from_kva(apparent_kva, voltage_kv)
            recommended_current_a = required_current_a * 1.1 if required_current_a > 0 else None
            recommended_linecode = (
                self._recommend_linecode_for_current(recommended_current_a)
                if recommended_current_a is not None
                else None
            )
            status = "ok"
            message = ""
            if required_current_a > normamps:
                status = "insufficient"
                message = (
                    f"按下游容量估算电流 {required_current_a:.1f} A，高于当前额定 {normamps:.1f} A。"
                    f"建议额定电流不低于 {recommended_current_a:.1f} A。"
                )
            elif required_current_a > 0:
                message = f"按下游容量估算电流 {required_current_a:.1f} A，未超过当前额定 {normamps:.1f} A。"

            index[edge_id] = {
                "line_voltage_kv": voltage_kv,
                "downstream_transformer_kva": downstream_transformer_kva,
                "downstream_load_kva": downstream_load_kva,
                "downstream_apparent_kva": apparent_kva,
                "estimated_required_current_a": required_current_a,
                "recommended_current_a": recommended_current_a,
                "recommended_linecode": recommended_linecode,
                "capacity_check_status": status,
                "capacity_check_message": message,
            }
        return index

    def _edge_voltage_kv(self, edge: dict[str, Any], from_node: dict[str, Any], to_node: dict[str, Any]) -> float:
        params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
        explicit = self._num(params.get("voltage_level_kv"), 0.0)
        if explicit > 0:
            return explicit
        from_kv = self._node_voltage_kv(from_node)
        to_kv = self._node_voltage_kv(to_node)
        positives = [kv for kv in (from_kv, to_kv) if kv > 0]
        return max(positives) if positives else self.base_kv

    def _recommend_linecode_for_current(self, required_current_a: float | None) -> str | None:
        if required_current_a is None or required_current_a <= 0:
            return None
        for name, defaults in sorted(self.LINE_CODES.items(), key=lambda item: float(item[1].get("normamps", 0.0))):
            if float(defaults.get("normamps", 0.0)) >= required_current_a:
                return name
        return "custom_parallel_or_busbar"

    def _count_by_key(self, rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(row.get(key) or "")
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _build_topology_case_summary(
        self,
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        editable_line_ids: list[str] = []
        skipped_transformer_connection_edge_ids: list[str] = []
        invalid_endpoint_edge_ids: list[str] = []
        normally_open_line_ids: list[str] = []

        for edge in edges:
            edge_id = self._safe_name(str(edge.get("id", "line")))
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                invalid_endpoint_edge_ids.append(edge_id)
                continue
            from_node = node_map[from_node_id]
            to_node = node_map[to_node_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                skipped_transformer_connection_edge_ids.append(edge_id)
                continue
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            editable_line_ids.append(edge_id)
            if self._bool(params.get("normally_open"), False):
                normally_open_line_ids.append(edge_id)

        return {
            "editable_line_ids": editable_line_ids,
            "editable_line_count": len(editable_line_ids),
            "normally_open_line_ids": normally_open_line_ids,
            "normally_open_line_count": len(normally_open_line_ids),
            "skipped_transformer_connection_edge_ids": skipped_transformer_connection_edge_ids,
            "skipped_transformer_connection_edge_count": len(skipped_transformer_connection_edge_ids),
            "invalid_endpoint_edge_ids": invalid_endpoint_edge_ids,
            "invalid_endpoint_edge_count": len(invalid_endpoint_edge_ids),
        }

    def _build_runtime_injection_contract(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        optimizable_load_count = sum(
            1
            for node in nodes
            if str(node.get("type")) == "load" and self._bool(self._params(node).get("optimize_storage"), False)
        )
        standalone_storage_count = sum(1 for node in nodes if str(node.get("type")) == "storage")
        storage_placeholder_count = sum(
            1
            for node in nodes
            if str(node.get("type")) == "load" and self._bool(self._params(node).get("storage_placeholder"), False)
        )
        return {
            "summary_kind": "structural_build_summary",
            "load_runtime_mode": "python_runtime_injection",
            "embedded_loadshape": False,
            "optimized_storage_mode": "solver_injected_at_target_bus",
            "optimizable_load_count": optimizable_load_count,
            "standalone_storage_mode": "exported_from_topology_storage_nodes",
            "standalone_storage_count": standalone_storage_count,
            "storage_placeholder_count": storage_placeholder_count,
            "notes": [
                "当前 visual_model 是静态网络骨架，逐时负荷状态由 Python 求解器在运行时写入 OpenDSS。",
                "优化目标储能默认不需要预先画成独立储能元件，求解阶段会在目标负荷母线动态注入 Storage 元件。",
                "只有已知且固定存在的现场储能资产，才建议在拓扑中作为独立 storage 节点建模。",
            ],
        }

    def validate_grid_health(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate grid infrastructure health: transformer capacity, voltage quality, tap adjustments."""
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        recommendations: list[dict[str, Any]] = []

        # Check transformer capacity
        for node in nodes:
            if not self._is_transformer_node(node):
                continue
            params = self._params(node)
            node_id = str(node.get("id", "tx"))
            rated_kva = self._num(params.get("rated_kva"), 1000.0 if self._is_distribution_transformer_node(node) else 31500.0)
            
            # Find connected load
            connected_load_kva = 0.0
            for edge in edges:
                from_id = str(edge.get("from_node_id", ""))
                to_id = str(edge.get("to_node_id", ""))
                other_id = to_id if from_id == node_id else (from_id if to_id == node_id else "")
                if other_id and other_id in node_map:
                    other_node = node_map[other_id]
                    if str(other_node.get("type")) == "load":
                        connected_load_kva += self._resource_apparent_power_kva(other_node)
            
            loading_pct = (connected_load_kva / rated_kva * 100) if rated_kva > 0 else 0
            
            if loading_pct > 100:
                errors.append(f"变压器 {node_id} 过载：额定 {rated_kva:.0f}kVA，实际负荷 {connected_load_kva:.0f}kVA（{loading_pct:.1f}%）")
                recommendations.append({
                    "type": "transformer_overload",
                    "node_id": node_id,
                    "message": f"变压器 {node_id} 过载 {loading_pct:.1f}%，建议增容至 {connected_load_kva * 1.2:.0f}kVA",
                    "rated_kva": rated_kva,
                    "load_kva": connected_load_kva,
                    "loading_pct": loading_pct,
                })
            elif loading_pct > 80:
                warnings.append(f"变压器 {node_id} 负载率偏高：{loading_pct:.1f}%")
            
            checks.append({
                "name": f"transformer_{node_id}_capacity",
                "status": "fail" if loading_pct > 100 else ("warn" if loading_pct > 80 else "pass"),
                "detail": f"变压器 {node_id}：额定 {rated_kva:.0f}kVA，负荷 {connected_load_kva:.0f}kVA，负载率 {loading_pct:.1f}%",
            })
            
            # Tap adjustment recommendation for voltage regulation
            tap = self._num(params.get("tap"), 1.0)
            if abs(tap - 1.0) < 0.001:
                recommendations.append({
                    "type": "tap_adjustment",
                    "node_id": node_id,
                    "message": f"变压器 {node_id} 当前分接头为 1.0，可调整至 1.05 提升低压侧电压 5%",
                    "current_tap": tap,
                    "recommended_tap": 1.05,
                })

        # Check for reactive power compensation needs
        load_nodes = [n for n in nodes if str(n.get("type")) == "load"]
        total_load_kw = sum(self._num(self._params(n).get("design_kw"), 0.0) for n in load_nodes)
        total_load_kvar = sum(
            self._num(self._params(n).get("kvar"), 
                     self._num(self._params(n).get("design_kw"), 0.0) * self._num(self._params(n).get("q_to_p_ratio"), 0.25))
            for n in load_nodes
        )
        
        if total_load_kvar > total_load_kw * 0.3:
            warnings.append(f"系统无功功率偏高：{total_load_kvar:.0f}kvar（有功 {total_load_kw:.0f}kW）")
            recommended_kvar = total_load_kvar * 0.5
            recommendations.append({
                "type": "reactive_compensation",
                "message": f"建议在重负荷节点安装无功补偿装置，容量约 {recommended_kvar:.0f}kvar",
                "total_load_kvar": total_load_kvar,
                "recommended_kvar": recommended_kvar,
            })
        
        checks.append({
            "name": "reactive_power_balance",
            "status": "warn" if total_load_kvar > total_load_kw * 0.3 else "pass",
            "detail": f"系统无功功率：{total_load_kvar:.0f}kvar，有功功率：{total_load_kw:.0f}kW",
        })

        return {
            "passed": len(errors) == 0,
            "checks": checks,
            "warnings": warnings,
            "errors": errors,
            "recommendations": recommendations,
            "summary": {
                "transformer_count": sum(1 for n in nodes if self._is_transformer_node(n)),
                "overloaded_transformer_count": sum(1 for c in checks if c["name"].startswith("transformer_") and c["status"] == "fail"),
                "total_load_kw": total_load_kw,
                "total_load_kvar": total_load_kvar,
            },
        }

    def _probe_opendss_compile(self, master_path: Path) -> dict[str, Any]:
        probe = {
            "mode": "best_effort_subprocess_probe",
            "attempted": False,
            "status": "skipped",
            "engine": "OpenDSS COM",
            "compile_succeeded": False,
            "solve_executed": False,
            "solve_converged": False,
            "circuit_name": "",
            "bus_count": 0,
            "line_count": 0,
            "load_count": 0,
            "compile_result": "",
            "solve_result": "",
            "message": "",
            "stderr_tail": "",
        }
        if not master_path.exists():
            probe["message"] = f"Master.dss 不存在：{master_path}"
            return probe

        script = """
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

result = {
    "attempted": False,
    "status": "skipped",
    "engine": "OpenDSS COM",
    "compile_succeeded": False,
    "solve_executed": False,
    "solve_converged": False,
    "circuit_name": "",
    "bus_count": 0,
    "line_count": 0,
    "load_count": 0,
    "compile_result": "",
    "solve_result": "",
    "message": "",
}

master_path = sys.argv[1]
dss = None
text = None
circuit = None
solution = None
try:
    import win32com.client

    result["attempted"] = True
    dss = win32com.client.Dispatch("OpenDSSEngine.DSS")
    if not dss.Start(0):
        result["status"] = "failed"
        result["message"] = "OpenDSS COM 引擎启动失败。"
    else:
        text = dss.Text
        text.Command = f"Compile [{master_path}]"
        result["compile_result"] = str(getattr(text, "Result", "") or "")

        circuit = dss.ActiveCircuit
        solution = circuit.Solution
        result["circuit_name"] = str(getattr(circuit, "Name", "") or "")
        try:
            result["bus_count"] = len(list(circuit.AllBusNames))
        except Exception:
            result["bus_count"] = 0
        try:
            result["line_count"] = len(list(circuit.Lines.AllNames))
        except Exception:
            result["line_count"] = 0
        try:
            result["load_count"] = len(list(circuit.Loads.AllNames))
        except Exception:
            result["load_count"] = 0

        result["compile_succeeded"] = bool(result["circuit_name"] or result["bus_count"] > 0)

        text.Command = "Solve"
        result["solve_result"] = str(getattr(text, "Result", "") or "")
        result["solve_executed"] = True
        result["solve_converged"] = bool(getattr(solution, "Converged", False))

        if result["compile_succeeded"] and result["solve_converged"]:
            result["status"] = "passed"
            result["message"] = "OpenDSS Compile/Solve 成功且潮流收敛。"
        elif result["compile_succeeded"]:
            result["status"] = "failed"
            result["message"] = "OpenDSS Compile 已完成，但 Solve 未收敛。"
        else:
            result["status"] = "failed"
            result["message"] = "OpenDSS Compile 未返回有效电路。"
except Exception as exc:
    result["status"] = "skipped"
    result["message"] = f"{type(exc).__name__}: {exc}"
finally:
    solution = None
    circuit = None
    text = None
    dss = None

print(json.dumps(result, ensure_ascii=False), flush=True)
""".strip()

        try:
            probe_env = {
                **os.environ,
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            }
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "-c", script, str(master_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=probe_env,
            )
        except Exception as exc:
            probe["message"] = f"OpenDSS probe 启动失败：{type(exc).__name__}: {exc}"
            return probe

        stdout_text = (completed.stdout or "").strip()
        stderr_text = (completed.stderr or "").strip()
        if stderr_text:
            probe["stderr_tail"] = stderr_text[-2000:]

        if stdout_text:
            last_line = stdout_text.splitlines()[-1]
            try:
                payload = json.loads(last_line)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                probe.update(payload)
        if completed.returncode not in {0, None}:
            if probe["status"] == "passed":
                probe["status"] = "failed"
                probe["message"] = f"OpenDSS probe 子进程异常退出（返回码 {completed.returncode}）。"
            elif probe["status"] == "skipped":
                probe["message"] = probe["message"] or f"OpenDSS probe 进程返回码 {completed.returncode}"
        return probe

    def _build_structural_checks(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
        artifacts: list[dict[str, Any]],
        bus_map: dict[str, Any],
        line_summary: list[dict[str, Any]],
        topology_case_summary: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        errors: list[str] = []
        check_warnings: list[str] = []

        artifact_names = {str(item.get("relative_path") or "") for item in artifacts}
        required_artifacts = {
            "Circuit.dss",
            "Source.dss",
            "Transformers.dss",
            "LineCodes_Custom.dss",
            "Lines_Main.dss",
            "TieLines.dss",
            "Loads_Runtime.dss",
            "Storage_Case.dss",
            "Topology_Case.dss",
            "Master.dss",
        }
        missing_artifacts = sorted(name for name in required_artifacts if name not in artifact_names)
        self._append_check(
            checks,
            name="required_artifacts_present",
            passed=not missing_artifacts,
            detail="全部核心 DSS 文件均已生成。" if not missing_artifacts else f"缺少文件：{', '.join(missing_artifacts)}",
        )
        if missing_artifacts:
            errors.append(f"缺少核心 DSS 文件：{', '.join(missing_artifacts)}")

        duplicate_buses = self._find_duplicate_values(
            [str(item.get("bus") or "") for item in bus_map.values() if isinstance(item, dict)]
        )
        self._append_check(
            checks,
            name="bus_names_unique",
            passed=not duplicate_buses,
            detail="母线命名唯一。" if not duplicate_buses else f"重复母线：{', '.join(duplicate_buses)}",
        )
        if duplicate_buses:
            errors.append(f"存在重复 OpenDSS 母线名：{', '.join(duplicate_buses)}")

        duplicate_load_names = self._find_duplicate_values(
            [self._load_name(node) for node in nodes if str(node.get("type")) == "load"]
        )
        self._append_check(
            checks,
            name="load_names_unique",
            passed=not duplicate_load_names,
            detail="负荷元件命名唯一。" if not duplicate_load_names else f"重复负荷名：{', '.join(duplicate_load_names)}",
        )
        if duplicate_load_names:
            errors.append(f"存在重复 OpenDSS 负荷名：{', '.join(duplicate_load_names)}")

        line_ids = {str(item.get("id") or "") for item in line_summary}
        topology_case_targets = set(topology_case_summary.get("editable_line_ids") or [])
        missing_topology_case_targets = sorted(target for target in topology_case_targets if target not in line_ids)
        self._append_check(
            checks,
            name="topology_case_targets_exist",
            passed=not missing_topology_case_targets,
            detail=(
                "Topology_Case.dss 仅编辑已生成的 Line 元件。"
                if not missing_topology_case_targets
                else f"Topology_Case.dss 引用了未生成的 Line：{', '.join(missing_topology_case_targets)}"
            ),
        )
        if missing_topology_case_targets:
            errors.append(f"Topology_Case.dss 引用了未生成的 Line：{', '.join(missing_topology_case_targets)}")

        invalid_endpoint_edge_ids = list(topology_case_summary.get("invalid_endpoint_edge_ids") or [])
        self._append_check(
            checks,
            name="edge_endpoints_valid",
            passed=not invalid_endpoint_edge_ids,
            detail="所有线路端点都能映射到有效节点。" if not invalid_endpoint_edge_ids else f"非法端点线路：{', '.join(invalid_endpoint_edge_ids)}",
        )
        if invalid_endpoint_edge_ids:
            errors.append(f"存在非法端点线路：{', '.join(invalid_endpoint_edge_ids)}")

        has_grid = any(self._is_grid_node(node) for node in nodes)
        has_transformer = any(self._is_transformer_node(node) for node in nodes)
        has_load = any(str(node.get("type")) == "load" for node in nodes)
        self._append_check(checks, "grid_node_present", has_grid, "已检测到上级电网/电源节点。" if has_grid else "未检测到上级电网/电源节点。")
        self._append_check(checks, "transformer_node_present", has_transformer, "已检测到主变/配变节点。" if has_transformer else "未检测到主变/配变节点。")
        self._append_check(checks, "load_node_present", has_load, "已检测到负荷节点。" if has_load else "未检测到负荷节点。")
        if not has_grid:
            errors.append("未检测到上级电网/电源节点。")
        if not has_transformer:
            errors.append("未检测到主变/配变节点。")
        if not has_load:
            check_warnings.append("未检测到负荷节点。")

        skipped_transformer_connection_edge_count = int(topology_case_summary.get("skipped_transformer_connection_edge_count") or 0)
        self._append_check(
            checks,
            name="transformer_connection_edges_skipped",
            passed=True,
            detail=f"共有 {skipped_transformer_connection_edge_count} 条连接由 Transformer 绕组表示，未重复导出为 Line。",
        )

        all_warnings = list(dict.fromkeys([*warnings, *check_warnings]))
        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "warnings": all_warnings,
            "checks": checks,
        }

    def _append_check(self, checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "name": name,
                "status": "pass" if passed else "fail",
                "detail": detail,
            }
        )

    def _find_duplicate_values(self, values: list[str]) -> list[str]:
        counts: dict[str, int] = {}
        for raw in values:
            value = str(raw or "").strip()
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
        return sorted(value for value, count in counts.items() if count > 1)

    def _params(self, node: dict[str, Any]) -> dict[str, Any]:
        return node.get("params") if isinstance(node.get("params"), dict) else {}

    def _bus_name(self, node: dict[str, Any]) -> str:
        params = self._params(node)
        explicit = str(params.get("dss_bus_name") or params.get("bus_name") or "").strip()
        if explicit:
            return self._safe_name(explicit)
        node_id = self._safe_name(str(node.get("id", "node")))
        if self._is_grid_node(node):
            return self._safe_name(str(params.get("source_bus") or "sourcebus"))
        if self._is_transformer_node(node):
            default_bus = f"{self._safe_name(str(node.get('id', 'tx')))}_lv" if self._is_distribution_transformer_node(node) else "n0"
            return self._safe_name(str(params.get("secondary_bus_name") or default_bus))
        if str(node.get("type")) == "load":
            registry_node_id = params.get("node_id")
            if registry_node_id not in (None, ""):
                return self._safe_name(f"n{int(self._num(registry_node_id, 0))}")
        return node_id

    def _load_name(self, node: dict[str, Any]) -> str:
        params = self._params(node)
        explicit = str(params.get("dss_load_name") or params.get("load_name") or "").strip()
        if explicit:
            return self._safe_name(explicit)
        node_id = params.get("node_id")
        if node_id not in (None, ""):
            return self._safe_name(f"LD{int(self._num(node_id, 0)):02d}")
        return self._safe_name(str(node.get("id", "load")))

    def _is_grid_node(self, node: dict[str, Any]) -> bool:
        return str(node.get("type")).strip().lower() in {"grid", "source"}

    def _is_transformer_node(self, node: dict[str, Any]) -> bool:
        return str(node.get("type")).strip().lower() in {"transformer", "distribution_transformer"}

    def _is_distribution_transformer_node(self, node: dict[str, Any]) -> bool:
        node_type = str(node.get("type")).strip().lower()
        if node_type == "distribution_transformer":
            return True
        if node_type != "transformer":
            return False
        params = self._params(node)
        role = str(params.get("transformer_role") or params.get("role") or "").strip().lower()
        return role in {"distribution", "distribution_transformer", "customer_distribution"} or self._bool(
            params.get("is_distribution_transformer"),
            False,
        )

    def _is_low_side_resource_node(self, node: dict[str, Any]) -> bool:
        return str(node.get("type")).strip().lower() in {"load", "storage", "pv", "wind", "capacitor"}

    def _distribution_service_edge_nodes(
        self,
        from_node: dict[str, Any],
        to_node: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if self._is_distribution_transformer_node(from_node) and self._is_low_side_resource_node(to_node):
            return from_node, to_node
        if self._is_distribution_transformer_node(to_node) and self._is_low_side_resource_node(from_node):
            return to_node, from_node
        return None

    def _distribution_service_edge_profile(
        self,
        edge: dict[str, Any],
        from_node: dict[str, Any],
        to_node: dict[str, Any],
    ) -> dict[str, float | str] | None:
        pair = self._distribution_service_edge_nodes(from_node, to_node)
        if pair is None:
            return None

        tx_node, resource_node = pair
        tx_params = self._params(tx_node)
        phases = self._edge_phases(edge, from_node, to_node)
        secondary_kv = self._distribution_voltage_kv_for_opendss(tx_params.get("voltage_level_kv"), phases)
        if secondary_kv <= 0:
            secondary_kv = self._node_voltage_kv(resource_node)

        transformer_kva = self._num(tx_params.get("rated_kva"), 1000.0)
        transformer_current_a = self._three_phase_current_from_kva(transformer_kva, secondary_kv)
        resource_kva = self._resource_apparent_power_kva(resource_node)
        resource_current_a = self._three_phase_current_from_kva(
            resource_kva,
            secondary_kv,
        )
        if transformer_current_a <= 0 and resource_current_a <= 0:
            return None

        # This line is a reduced-model service connection behind a dedicated customer transformer.
        normamps = max(
            transformer_current_a,
            resource_current_a * self.SERVICE_LINE_RESOURCE_MARGIN,
            self.SERVICE_LINE_MIN_RATED_A,
        )
        emergamps = max(
            normamps * self.SERVICE_LINE_EMERGENCY_MARGIN,
            transformer_current_a * self.SERVICE_LINE_TRANSFORMER_EMERGENCY_MARGIN,
            normamps,
        )
        # For high-current 0.4 kV service connections, a single cable's R1 is unrealistically
        # high. Real installations use parallel cables → use OpenDSS 8500Bus/WireData.dss
        # parallel-cable formula: R_eq = R_single / n, X_eq = X_single / n.
        if normamps >= self.SERVICE_LINE_LOW_Z_CURRENT_THRESHOLD_A and secondary_kv < 1.0:
            cable_entry = self._select_parallel_cable(normamps)
            r1_eq = cable_entry["rac"] / cable_entry["parallel"]
            x1_eq = r1_eq * self.WIRE_XR_RATIO
            r0_eq = r1_eq  # zero-sequence same as pos-seq for copper
            x0_eq = x1_eq
            profile = {
                "linecode": "",  # empty → _build_lines uses explicit r1/x1
                "equivalent_mode": "parallel_cable_equivalent",
                "default_length_km": self.SERVICE_LINE_DEFAULT_LENGTH_KM,
                "secondary_kv": secondary_kv,
                "transformer_kva": transformer_kva,
                "resource_kva": resource_kva,
                "transformer_current_a": transformer_current_a,
                "resource_current_a": resource_current_a,
                "normamps": normamps,
                "emergamps": emergamps,
                "r1": r1_eq,
                "x1": x1_eq,
                "r0": r0_eq,
                "x0": x0_eq,
                "c1": 0.0,
                "c0": 0.0,
                "cable_name": cable_entry["name"],
                "cable_parallel": cable_entry["parallel"],
                "parallel_note": cable_entry["note"],
            }
        else:
            profile = {
                "linecode": self.SERVICE_LINE_LINECODE,
                "equivalent_mode": "standard_linecode",
                "default_length_km": self.SERVICE_LINE_DEFAULT_LENGTH_KM,
                "secondary_kv": secondary_kv,
                "transformer_kva": transformer_kva,
                "resource_kva": resource_kva,
                "transformer_current_a": transformer_current_a,
                "resource_current_a": resource_current_a,
                "normamps": normamps,
                "emergamps": emergamps,
            }
        return profile

    def _is_transformer_connection_edge(self, from_node: dict[str, Any], to_node: dict[str, Any]) -> bool:
        if self._is_grid_node(from_node) and self._is_transformer_node(to_node):
            return True
        if self._is_grid_node(to_node) and self._is_transformer_node(from_node):
            return True
        if self._is_distribution_transformer_node(to_node) and not self._is_low_side_resource_node(from_node):
            return True
        if self._is_distribution_transformer_node(from_node) and not self._is_low_side_resource_node(to_node):
            return True
        return False

    def _infer_transformer_primary_bus(
        self,
        node: dict[str, Any],
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
        default_bus: str,
    ) -> str:
        params = self._params(node)
        explicit = str(params.get("primary_bus_name") or "").strip()
        if explicit:
            return self._safe_name(explicit)
        node_id = str(node.get("id") or "")
        for edge in edges:
            from_id = str(edge.get("from_node_id") or "")
            to_id = str(edge.get("to_node_id") or "")
            other_id = ""
            if to_id == node_id:
                other_id = from_id
            elif from_id == node_id and self._is_distribution_transformer_node(node):
                other_id = to_id
            if not other_id or other_id not in node_map:
                continue
            other_node = node_map[other_id]
            if self._is_distribution_transformer_node(node) and self._is_low_side_resource_node(other_node):
                continue
            return self._bus_name(other_node)
        return self._safe_name(default_bus)

    def _node_voltage_kv(self, node: dict[str, Any]) -> float:
        params = self._params(node)
        node_type = str(node.get("type")).strip().lower()
        if self._is_grid_node(node):
            return self._source_voltage_kv(node, 3)
        if node_type == "load":
            return self._distribution_voltage_kv_for_opendss(params.get("target_kv_ln"), 3)
        if node_type in {"pv", "wind", "storage", "capacitor", "switch", "breaker", "fuse", "regulator"}:
            return self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), 3)
        return self._num(params.get("voltage_level_kv"), self.base_kv)

    def _source_voltage_kv(self, node: dict[str, Any] | None, phases: int) -> float:
        params = self._params(node or {})
        raw = params.get("base_kv")
        if raw in (None, ""):
            return 110.0
        kv = self._num(raw, 110.0)
        if abs(kv - 110.0 / math.sqrt(3.0)) <= 0.5:
            return 110.0
        return kv

    def _load_voltage_kv_for_opendss(self, params: dict[str, Any], phases: int) -> float:
        raw = params.get("target_kv_ln")
        return self._distribution_voltage_kv_for_opendss(raw, phases)

    def _distribution_voltage_kv_for_opendss(self, value: Any, phases: int) -> float:
        kv = self._num(value, self.base_kv)
        base_ln = float(self.base_kv) / math.sqrt(3.0)
        if kv > 0 and abs(kv - base_ln) <= max(0.02, base_ln * 0.03):
            return float(self.base_kv)
        return kv

    def _resource_apparent_power_kva(self, node: dict[str, Any]) -> float:
        params = self._params(node)
        node_type = str(node.get("type")).strip().lower()
        if node_type == "load":
            kw = self._num(params.get("design_kw"), 0.0)
            kvar = self._num(params.get("kvar"), kw * self._num(params.get("q_to_p_ratio"), 0.25))
            return math.hypot(kw, kvar)
        if node_type == "storage":
            kva = self._num(params.get("kva"), 0.0)
            if kva > 0:
                return kva
            rated_kw = self._num(params.get("rated_kw"), 0.0)
            return max(rated_kw, self._num(params.get("rated_kwh"), 0.0))
        if node_type == "pv":
            return self._num(params.get("kva"), self._num(params.get("pmpp_kw"), self._num(params.get("rated_kw"), 0.0)))
        if node_type == "wind":
            rated_kw = self._num(params.get("rated_kw"), 0.0)
            pf = abs(self._num(params.get("pf"), 0.98))
            if pf <= 0:
                return rated_kw
            return rated_kw / min(pf, 1.0)
        if node_type == "capacitor":
            return abs(self._num(params.get("kvar"), 0.0))
        return 0.0

    @staticmethod
    def _three_phase_current_from_kva(kva: float, kv_ll: float) -> float:
        if kva <= 0 or kv_ll <= 0:
            return 0.0
        return float(kva) / (math.sqrt(3.0) * float(kv_ll))

    def _select_parallel_cable(self, required_ampacity_a: float) -> dict[str, float | str]:
        """
        Select copper cable size and number of parallel conductors to meet required ampacity.
        Uses OpenDSS 8500Bus/WireData.dss copper conductor parameters.

        Returns a dict with keys: name, rac, gmr, radius, normamps, emergamps, parallel.
        The effective impedance after paralleling is rac/parallel, x1/parallel.
        """
        candidates: list[tuple[str, float, int]] = []
        for name, entry in self.WIRE_DATA_CU.items():
            single_amp = float(entry["normamps"])
            if single_amp <= 0:
                continue
            # Find minimum parallel count to meet ampacity
            n = math.ceil(required_ampacity_a / single_amp)
            if n < 1:
                n = 1
            total_amp = single_amp * n
            candidates.append((name, total_amp, n))

        if not candidates:
            # Fallback: use 1000_CU x1
            return {
                "name": "1000_CU",
                "rac": 0.042875,
                "gmr": 1.121921,
                "radius": 1.46177,
                "normamps": 1300.0,
                "emergamps": 1300.0,
                "parallel": 1,
                "note": "fallback",
            }

        # Pick the candidate with lowest total_amp >= required (i.e., just enough)
        best = min(candidates, key=lambda x: (x[1] < required_ampacity_a, x[1], x[2]))
        name, total_amp, n = best
        entry = self.WIRE_DATA_CU[name]
        return {
            "name": name,
            "rac": float(entry["rac"]),
            "gmr": float(entry["gmr"]),
            "radius": float(entry["radius"]),
            "normamps": float(entry["normamps"]) * n,
            "emergamps": float(entry["emergamps"]) * n,
            "parallel": n,
            "note": "equivalent_parallel_cable_count; not a construction drawing" if n > 12 else "parallel_cable_count",
        }

    @staticmethod
    def _line_to_neutral_if_common_ll(kv: float) -> float:
        if kv <= 0:
            return kv
        for nominal_ll in (6.0, 6.3, 10.0, 20.0, 35.0, 66.0, 110.0, 220.0):
            if abs(kv - nominal_ll) <= max(0.03, nominal_ll * 0.02):
                return kv / math.sqrt(3.0)
        return kv

    def _voltage_bases(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[float]:
        phases = self._topology_phases(nodes, edges)
        source_node = next((node for node in nodes if self._is_grid_node(node)), None)
        values: list[float] = [self._source_voltage_kv(source_node, phases)]
        for node in nodes:
            if not self._is_transformer_node(node):
                continue
            params = self._params(node)
            values.append(self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), phases))
            if params.get("primary_voltage_kv") not in (None, ""):
                values.append(self._distribution_voltage_kv_for_opendss(params.get("primary_voltage_kv"), phases))
        for node in nodes:
            if self._is_grid_node(node) or self._is_transformer_node(node):
                continue
            kv = self._node_voltage_kv(node)
            if kv > 0:
                values.append(kv)
        if len(values) == 1:
            values.append(self._distribution_voltage_kv_for_opendss(self.base_kv, phases))

        out: list[float] = []
        for value in values:
            if value <= 0:
                continue
            if not any(abs(value - existing) <= max(0.001, existing * 0.001) for existing in out):
                out.append(float(value))
        return out or [self.base_kv]

    def _safe_name(self, raw: str) -> str:
        out = []
        for ch in raw:
            if ch.isalnum() or ch == "_":
                out.append(ch)
            else:
                out.append("_")
        return "".join(out).strip("_") or "unnamed"

    def _topology_phases(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> int:
        return 3

    def _node_phases(self, node: dict[str, Any] | None, default: int = 3) -> int:
        return 3

    def _edge_phases(self, edge: dict[str, Any], from_node: dict[str, Any], to_node: dict[str, Any]) -> int:
        return 3

    def _phase_suffix(self, phases: int) -> str:
        return ".1.2.3"

    def _bool(self, value: Any, default: bool) -> bool:
        if value in (None, ""):
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "是", "启用"}:
            return True
        if text in {"0", "false", "no", "n", "off", "否", "停用"}:
            return False
        return bool(default)

    @staticmethod
    def _dss_connection(value: Any, default: str) -> str:
        text = str(value or default).strip().lower()
        if text in {"delta", "d"}:
            return "delta"
        return "wye"

    def _num(self, value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        if parsed != parsed:
            return float(default)
        return parsed
