from __future__ import annotations

import hashlib
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

    Electrical DSS parameters must come from the frontend topology, asset binding, imports,
    or runtime manifest. Missing electrical fields are reported as model-review errors instead
    of being silently filled by backend templates.
    """

    OFFICIAL_DOC_REFERENCES: list[dict[str, str]] = [
        {
            "objects": "Circuit, Vsource, Solution, COM Interface",
            "url": "https://opendss.epri.com/COMInterface.html",
            "confirmed": "DSS Text 命令驱动 Compile/Solve；Solution.Converged 用于判断潮流是否收敛。",
        },
        {
            "objects": "Line, LineCode, WireData, LineGeometry",
            "url": "https://opendss.epri.com/Line.html",
            "confirmed": "线路必须明确选择 LineCode、显式阻抗或 Geometry/WireData 之一；载流量用于过载校核。",
        },
        {
            "objects": "Transformer, XfmrCode",
            "url": "https://opendss.epri.com/Properties16.html",
            "confirmed": "Transformer 需要绕组 bus、kV、kVA、conn、%R 和 xhl 等阻抗信息。",
        },
        {
            "objects": "Load, LoadShape",
            "url": "https://opendss.epri.com/Properties7.html",
            "confirmed": "Load 的 kV、kW 以及 kvar 或 PF 必须明确；LoadShape 与运行时 Edit 不能重复表达同一时序负荷。",
        },
        {
            "objects": "PVSystem",
            "url": "https://opendss.epri.com/PVSystem.html",
            "confirmed": "PVSystem 的 bus、phases、kV、kVA、Pmpp、无功模式和 irradiance/曲线均影响潮流模型。",
        },
        {
            "objects": "Storage, StorageController",
            "url": "https://opendss.epri.com/Storage.html",
            "confirmed": "Storage 使用 kWrated/kWhrated/%stored/%reserve/state/dispmode 表达容量、SOC 和外部调度状态。",
        },
        {
            "objects": "Capacitor, RegControl, Fuse, Recloser, Monitor, EnergyMeter",
            "url": "https://opendss.epri.com/RegControl.html",
            "confirmed": "控制、保护和监测对象只有在用户明确提供对象与参数时才应生成。",
        },
    ]

    FRONTEND_LINE_CODE_LIBRARY: dict[str, dict[str, float]] = {
        "LC_MAIN": {
            "r_ohm_per_km": 0.251742424,
            "x_ohm_per_km": 0.255208333,
            "r0_ohm_per_km": 0.251742424,
            "x0_ohm_per_km": 0.255208333,
            "c1_nf_per_km": 2.270366128,
            "c0_nf_per_km": 2.270366128,
        },
        "LC_BRANCH": {
            "r_ohm_per_km": 0.363958,
            "x_ohm_per_km": 0.269167,
            "r0_ohm_per_km": 0.363958,
            "x0_ohm_per_km": 0.269167,
            "c1_nf_per_km": 2.1922,
            "c0_nf_per_km": 2.1922,
        },
        "LC_CABLE": {
            "r_ohm_per_km": 0.254261364,
            "x_ohm_per_km": 0.097045455,
            "r0_ohm_per_km": 0.254261364,
            "x0_ohm_per_km": 0.097045455,
            "c1_nf_per_km": 44.70661522,
            "c0_nf_per_km": 44.70661522,
        },
        "LC_LIGHT": {
            "r_ohm_per_km": 0.530208,
            "x_ohm_per_km": 0.281345,
            "r0_ohm_per_km": 0.530208,
            "x0_ohm_per_km": 0.281345,
            "c1_nf_per_km": 2.12257,
            "c0_nf_per_km": 2.12257,
        },
    }
    LOAD_MODEL_DEFAULT = 1
    LOAD_CONNECTION_DEFAULT = "wye"
    COMMON_LINE_LINE_KV = (0.4, 6.0, 6.3, 10.0, 20.0, 35.0, 66.0, 110.0, 220.0)

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
        model_review = self._build_model_review(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
            node_map=node_map,
            output_path=output_path,
        )
        linecodes_text = self._build_linecodes(edges, node_map)
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
                ).__dict__ | {"sha256": self._sha256_text(content)}
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
            model_review=model_review,
        )
        if structural_checks.get("errors"):
            opendss_probe = self._blocked_opendss_probe(
                "建模审查或 DSS 结构自检存在 error，未执行 OpenDSS Compile/Solve 探针。"
            )
        else:
            opendss_probe = self._probe_opendss_compile(output_path / "Master.dss")
        model_review = self._finalize_model_review(
            review=model_review,
            artifacts=artifacts,
            structural_checks=structural_checks,
            opendss_probe=opendss_probe,
            output_path=output_path,
        )
        review_json_path = output_path / "opendss_model_review.json"
        review_md_path = output_path / "opendss_model_review.md"
        review_json_path.write_text(json.dumps(model_review, ensure_ascii=False, indent=2), encoding="utf-8")
        review_md_path.write_text(self._render_model_review_markdown(model_review), encoding="utf-8")
        artifacts.extend(
            [
                {
                    "relative_path": "opendss_model_review.json",
                    "absolute_path": str(review_json_path),
                    "exists": True,
                    "sha256": self._sha256_text(review_json_path.read_text(encoding="utf-8")),
                },
                {
                    "relative_path": "opendss_model_review.md",
                    "absolute_path": str(review_md_path),
                    "exists": True,
                    "sha256": self._sha256_text(review_md_path.read_text(encoding="utf-8")),
                },
            ]
        )
        summary = {
            "project_id": project_id,
            "base_kv": self.base_kv,
            "voltage_bases": voltage_bases,
            "source_bus": self._bus_name(source_node) if source_node else "sourcebus",
            "phase_count": phase_count,
            "linecode_count": self._count_user_linecodes(edges),
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
            "line_count_by_code": self._count_by_key(line_summary, "linecode", empty_label="EXPLICIT_IMPEDANCE"),
            "topology_case_summary": topology_case_summary,
            "runtime_injection_contract": runtime_injection_contract,
            "structural_checks": structural_checks,
            "opendss_probe": opendss_probe,
            "opendss_model_review": {
                "status": model_review.get("status"),
                "issue_count": len(model_review.get("issues") or []),
                "error_count": sum(1 for item in model_review.get("issues") or [] if item.get("level") == "error"),
                "json_path": str(review_json_path),
                "markdown_path": str(review_md_path),
            },
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
        pu = self._num(params.get("pu"), 0.0)
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
        pu = self._num(params.get("pu"), 0.0)
        phases = self._node_phases(source_node, self._topology_phases(nodes, [])) if source_node else self._topology_phases(nodes, [])
        base_kv = self._source_voltage_kv(source_node, phases)
        source_bus = self._bus_name(source_node) if source_node else "sourcebus"
        mvasc3 = self._num(params.get("mvasc3"), 0.0)
        mvasc1 = self._num(params.get("mvasc1"), mvasc3)
        x1r1 = self._num(params.get("x1r1"), 0.0)
        x0r0 = self._num(params.get("x0r0"), 0.0)
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

    def _build_linecodes(self, edges: list[dict[str, Any]], node_map: dict[str, dict[str, Any]]) -> str:
        lines = [
            "! Project line code library",
            "! Only user-provided line codes are written here.",
        ]
        emitted: set[str] = set()
        for edge in edges:
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            linecode = str(params.get("linecode") or params.get("line_code") or "").strip()
            if not linecode or linecode in emitted:
                continue
            from_node_id = str(edge.get("from_node_id", "")).strip()
            to_node_id = str(edge.get("to_node_id", "")).strip()
            if from_node_id not in node_map or to_node_id not in node_map:
                continue
            if self._is_transformer_connection_edge(node_map[from_node_id], node_map[to_node_id]):
                continue
            if self._bus_name(node_map[from_node_id]) == self._bus_name(node_map[to_node_id]):
                continue
            values = self._linecode_electrical_values(linecode, params)
            emitted.add(linecode)
            lines.extend(
                [
                    f"New LineCode.{self._safe_name(linecode)} nphases={self._edge_phases(edge, node_map[from_node_id], node_map[to_node_id])} BaseFreq=50 Units=km",
                    f"~ R1={values['r_ohm_per_km']:.9f} X1={values['x_ohm_per_km']:.9f} R0={values['r0_ohm_per_km']:.9f} X0={values['x0_ohm_per_km']:.9f}",
                    f"~ C1={values['c1_nf_per_km']:.9f} C0={values['c0_nf_per_km']:.9f}",
                    "",
                ]
            )
        if len(lines) == 2:
            lines.append("! no user line codes")
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
            rated_kva = self._num(params.get("rated_kva"), 0.0)
            sec_kv = self._distribution_voltage_kv_for_opendss(params.get("voltage_level_kv"), phases)
            pri_kv = self._source_voltage_kv(source_node, phases)
            if params.get("primary_voltage_kv") not in (None, ""):
                pri_kv = self._distribution_voltage_kv_for_opendss(params.get("primary_voltage_kv"), phases)
                if not is_customer_tx:
                    pri_kv = self._source_voltage_kv({"params": {"base_kv": params.get("primary_voltage_kv")}}, phases)
            primary_bus = self._infer_transformer_primary_bus(node, edges, node_map, source_bus)
            bus = self._bus_name(node)
            primary_conn = self._dss_connection(params.get("primary_conn"), "")
            secondary_conn = self._dss_connection(params.get("secondary_conn"), "")
            xhl = self._num(params.get("xhl_percent"), self._num(params.get("xhl"), 0.0))
            percent_r = self._num(params.get("percent_r"), self._num(params.get("r_percent"), 0.0))
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
            if from_bus == to_bus:
                lines.append(f"! skipped {edge_id}: both endpoints map to OpenDSS bus {from_bus}")
                continue
            phases = self._edge_phases(edge, from_node, to_node)
            length_km = self._num(params.get("length_km"), 0.0)
            units = str(params.get("units") or params.get("length_unit") or "").strip()
            if units.lower() in {"kilometer", "kilometers"}:
                units = "km"
            if not units:
                units = "km"

            linecode = str(
                params.get("linecode")
                or params.get("line_code")
                or ""
            ).strip()
            has_explicit_rx = self._has_value(params, "r_ohm_per_km") and self._has_value(params, "x_ohm_per_km")
            normamps = self._num(params.get("rated_current_a"), self._num(params.get("normamps"), 0.0))
            emergamps = self._num(params.get("emerg_current_a"), self._num(params.get("emergamps"), 0.0))
            enabled = "yes" if self._bool(params.get("enabled"), True) and not self._bool(params.get("normally_open"), False) else "no"

            if linecode:
                electrical = f"linecode={self._safe_name(linecode)}"
            elif has_explicit_rx:
                values = self._linecode_electrical_values(linecode, params)
                r_ohm_per_km = values["r_ohm_per_km"]
                x_ohm_per_km = values["x_ohm_per_km"]
                r0 = values["r0_ohm_per_km"]
                x0 = values["x0_ohm_per_km"]
                c1 = values["c1_nf_per_km"]
                c0 = values["c0_nf_per_km"]
                electrical = f"r1={r_ohm_per_km:g} x1={x_ohm_per_km:g} r0={r0:g} x0={x0:g} c1={c1:g} c0={c0:g}"
            else:
                lines.append(f"! skipped {edge_id}: missing user-provided LineCode or explicit impedance")
                continue

            lines.append(
                f"New Line.{edge_id} phases={phases} bus1={from_bus}{self._phase_suffix(phases)} bus2={to_bus}{self._phase_suffix(phases)} "
                f"length={length_km:g} units={units} {electrical} normamps={normamps:g} emergamps={emergamps:g} enabled={enabled}"
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
            pf = self._num(params.get("pf"), 0.0)
            model = self._load_model(params)
            conn = self._load_connection(params)
            bus = self._bus_name(node)
            kvar = self._num(params.get("kvar"), kw * self._num(params.get("q_to_p_ratio"), 0.0))
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
            pf = self._num(params.get("pf"), 0.0)
            if node_type == "pv":
                pmpp = self._num(params.get("pmpp_kw"), self._num(params.get("rated_kw"), 0.0))
                kva = self._num(params.get("kva"), 0.0)
                irradiance = self._num(params.get("irradiance"), 0.0)
                lines.append(
                    f"New PVSystem.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} kV={kv:g} kVA={kva:g} Pmpp={pmpp:g} pf={pf:g} irradiance={irradiance:g}"
                )
            else:
                kw = self._num(params.get("rated_kw"), 0.0)
                model = int(self._num(params.get("model"), 0))
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
            kvar = self._num(params.get("kvar"), 0.0)
            conn = self._dss_connection(params.get("connection"), "")
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
            winding = int(self._num(params.get("winding"), 0))
            vreg = self._num(params.get("vreg"), 0.0)
            band = self._num(params.get("band"), 0.0)
            ptratio = self._num(params.get("ptratio"), 0.0)
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
            protection_model = str(params.get("protection_model") or "").strip().lower()
            if node_type in {"switch", "breaker"} and protection_model not in {"fuse", "recloser"}:
                lines.append(f"Edit Line.{target_line} switch=yes enabled={enabled}")
            elif protection_model == "recloser":
                lines.append(
                    f"New Recloser.{name} MonitoredObj=Line.{target_line} "
                    f"MonitoredTerm={int(self._num(params.get('monitored_term'), 0))} "
                    f"SwitchedObj=Line.{target_line} SwitchedTerm={int(self._num(params.get('switched_term'), 0))} "
                    f"Shots={int(self._num(params.get('shots'), 0))} "
                    f"NumFast={int(self._num(params.get('num_fast'), 0))} enabled={enabled}"
                )
            elif protection_model == "fuse":
                rated_current = self._num(params.get("rated_current_a"), 0.0)
                lines.append(
                    f"New Fuse.{name} MonitoredObj=Line.{target_line} MonitoredTerm=1 SwitchedObj=Line.{target_line} SwitchedTerm=1 RatedCurrent={rated_current:g} enabled={enabled}"
                )
            else:
                lines.append(f"Edit Line.{target_line} switch=yes enabled={enabled}")
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
            if self._bus_name(from_node) == self._bus_name(to_node):
                lines.append(f"! skipped {edge_id}: both endpoints map to the same OpenDSS bus")
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
                power = self._num(params.get("rated_kw"), 0.0)
                energy = self._num(params.get("rated_kwh"), 0.0)
                reserve = self._num(params.get("reserve_soc_pct"), 0.0)
                stored = self._num(params.get("initial_soc_pct"), 0.0)
                charge_eff = self._num(params.get("charge_efficiency_pct"), self._num(params.get("charge_efficiency"), 0.0))
                discharge_eff = self._num(params.get("discharge_efficiency_pct"), self._num(params.get("discharge_efficiency"), 0.0))
                name = self._safe_name(str(params.get("dss_name") or node.get("id") or "storage"))
                lines.extend(
                    [
                        f"New Storage.{name} phases={phases} bus1={bus}{self._phase_suffix(phases)} conn=wye kV={kv:g}",
                        f"~ kWrated={power:g} kWhrated={energy:g} kVA={power:g}",
                        f"~ kW=0 kvar=0 %stored={stored:g} %reserve={reserve:g} %EffCharge={charge_eff:g} %EffDischarge={discharge_eff:g} state=idling dispmode=external",
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
            if self._bus_name(from_node) == self._bus_name(to_node):
                continue

            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            phases = self._edge_phases(edge, from_node, to_node)
            linecode = str(
                params.get("linecode")
                or params.get("line_code")
                or ""
            ).strip()
            normamps = self._num(params.get("rated_current_a"), self._num(params.get("normamps"), 0.0))
            emergamps = self._num(params.get("emerg_current_a"), self._num(params.get("emergamps"), 0.0))
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
                "length_km": self._num(params.get("length_km"), 0.0),
                "units": str(params.get("units") or params.get("length_unit") or "km"),
                "linecode": linecode,
                "normamps": normamps,
                "emergamps": emergamps,
                "enabled": enabled,
                "normally_open": self._bool(params.get("normally_open"), False),
                "impedance_source": "user_linecode" if linecode else ("user_explicit_impedance" if self._has_value(params, "r_ohm_per_km") and self._has_value(params, "x_ohm_per_km") else "missing"),
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
            from_node = node_map[from_node_id]
            to_node = node_map[to_node_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                continue
            if self._bus_name(from_node) == self._bus_name(to_node):
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
            if self._bus_name(from_node) == self._bus_name(to_node):
                continue

            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            normamps = self._num(params.get("rated_current_a"), self._num(params.get("normamps"), 0.0))

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
        return max(positives) if positives else 0.0

    def _recommend_linecode_for_current(self, required_current_a: float | None) -> str | None:
        if required_current_a is None or required_current_a <= 0:
            return None
        return None

    @staticmethod
    def _count_user_linecodes(edges: list[dict[str, Any]]) -> int:
        names: set[str] = set()
        for edge in edges:
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            name = str(params.get("linecode") or params.get("line_code") or "").strip()
            if name:
                names.add(name)
        return len(names)

    def _linecode_library_has(self, linecode: str, field: str) -> bool:
        library_row = self.FRONTEND_LINE_CODE_LIBRARY.get(str(linecode or "").strip())
        return isinstance(library_row, dict) and field in library_row

    def _linecode_electrical_values(self, linecode: str, params: dict[str, Any]) -> dict[str, float]:
        library_row = self.FRONTEND_LINE_CODE_LIBRARY.get(str(linecode or "").strip()) or {}
        values: dict[str, float] = {}
        for field in ("r_ohm_per_km", "x_ohm_per_km", "r0_ohm_per_km", "x0_ohm_per_km", "c1_nf_per_km", "c0_nf_per_km"):
            values[field] = self._num(params.get(field), self._num(library_row.get(field), 0.0))
        return values

    def _line_length_unit_is_explicit(self, params: dict[str, Any]) -> bool:
        if self._has_value(params, "units") or self._has_value(params, "length_unit"):
            return True
        return self._has_value(params, "length_km")

    def _load_model(self, params: dict[str, Any]) -> int:
        if self._has_value(params, "model"):
            return int(self._num(params.get("model"), self.LOAD_MODEL_DEFAULT))
        return self.LOAD_MODEL_DEFAULT

    def _load_connection(self, params: dict[str, Any]) -> str:
        if self._has_value(params, "connection"):
            return self._dss_connection(params.get("connection"), self.LOAD_CONNECTION_DEFAULT)
        return self.LOAD_CONNECTION_DEFAULT

    def _count_by_key(self, rows: list[dict[str, Any]], key: str, empty_label: str = "UNSPECIFIED") -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(row.get(key) or "").strip() or empty_label
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
            if self._bus_name(from_node) == self._bus_name(to_node):
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

    def _build_model_review(
        self,
        project_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        node_map: dict[str, dict[str, Any]],
        output_path: Path,
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        contract_rows: list[dict[str, Any]] = []
        field_sources: dict[str, int] = {"web_input": 0, "asset_binding": 0, "runtime_manifest": 0}

        def label(obj: dict[str, Any]) -> str:
            return str(obj.get("name") or obj.get("id") or "").strip() or "未命名对象"

        def add_issue(
            code: str,
            stage: str,
            object_type: str,
            object_id: str,
            message: str,
            suggestion: str,
            missing_fields: list[str] | None = None,
            dss_element: str = "",
            doc: str = "",
            level: str = "error",
        ) -> None:
            issues.append(
                {
                    "level": level,
                    "code": code,
                    "stage": stage,
                    "object_type": object_type,
                    "object_id": object_id,
                    "dss_element": dss_element,
                    "dss_file": "",
                    "message": message,
                    "suggestion": suggestion,
                    "missing_fields": missing_fields or [],
                    "official_doc_reference": doc,
                }
            )

        def require_fields(
            obj: dict[str, Any],
            params: dict[str, Any],
            fields: list[str],
            *,
            code: str,
            stage: str,
            object_type: str,
            suggestion: str,
            doc: str,
        ) -> list[str]:
            missing = [field for field in fields if not self._has_value(params, field)]
            object_id = str(obj.get("id") or "")
            for field in fields:
                if self._has_value(params, field):
                    field_sources["web_input"] += 1
            if missing:
                add_issue(
                    code=code,
                    stage=stage,
                    object_type=object_type,
                    object_id=object_id,
                    dss_element=self._safe_name(object_id),
                    message=f"{object_type} {label(obj)} 缺少 OpenDSS 建模字段：{', '.join(missing)}。",
                    suggestion=suggestion,
                    missing_fields=missing,
                    doc=doc,
                )
            contract_rows.append(
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "required_fields": fields,
                    "provided_fields": [field for field in fields if field not in missing],
                    "missing_fields": missing,
                    "source": "web_input",
                    "blocked": bool(missing),
                }
            )
            return missing

        grid_nodes = [node for node in nodes if self._is_grid_node(node)]
        if not grid_nodes:
            add_issue(
                "OPENDSS_TOPO_GRID_MISSING",
                "topology",
                "grid",
                "",
                "拓扑中缺少上级电网/电源节点，无法定义 Circuit/Vsource。",
                "请在拓扑编辑器中添加“电网/电源”节点，并填写 base_kv、pu、phases、mvasc3、mvasc1、x1r1、x0r0。",
                ["grid"],
                doc="Circuit/Vsource",
            )
        for node in grid_nodes:
            params = self._params(node)
            require_fields(
                node,
                params,
                ["source_bus", "base_kv", "pu", "phases", "mvasc3", "mvasc1", "x1r1", "x0r0"],
                code="OPENDSS_VSOURCE_SHORT_CIRCUIT_REQUIRED",
                stage="source",
                object_type="grid",
                suggestion="请在电网/电源节点补齐电源母线、电压、pu、相数、三相/单相短路容量和 X/R。",
                doc="Circuit/Vsource",
            )
            if not self._has_value(params, "x1r1") or not self._has_value(params, "x0r0"):
                add_issue(
                    "OPENDSS_VSOURCE_XR_REQUIRED",
                    "source",
                    "grid",
                    str(node.get("id") or ""),
                    f"电源 {label(node)} 缺少 X/R 参数。",
                    "请在电网/电源节点填写 x1r1 与 x0r0。",
                    [field for field in ("x1r1", "x0r0") if not self._has_value(params, field)],
                    doc="Vsource",
                )

        bus_names: dict[str, str] = {}
        element_names: dict[str, str] = {}
        for node in nodes:
            node_id = str(node.get("id") or "")
            node_type = str(node.get("type") or "")
            params = self._params(node)
            if node_type in {"grid", "source", "transformer", "distribution_transformer", "bus", "branch", "load", "pv", "storage", "capacitor"}:
                if not self._has_value(params, "phases"):
                    add_issue(
                        "OPENDSS_PHASE_REQUIRED",
                        "topology",
                        node_type,
                        node_id,
                        f"{node_type} {label(node)} 缺少相数/phases，不能自动假设三相。",
                        "请在拓扑对象参数中填写 phases=1、2 或 3。",
                        ["phases"],
                        doc="bus phase syntax",
                    )
                if node_type not in {"grid", "source", "transformer", "distribution_transformer"} and not (
                    self._has_value(params, "voltage_level_kv") or self._has_value(params, "target_kv_ln")
                ):
                    add_issue(
                        "OPENDSS_VOLTAGE_REQUIRED",
                        "topology",
                        node_type,
                        node_id,
                        f"{node_type} {label(node)} 缺少电压等级字段。",
                        "请在拓扑对象参数中填写 voltage_level_kv 或 target_kv_ln。",
                        ["voltage_level_kv"],
                        doc="kV property",
                    )
            bus_name = self._bus_name(node)
            if bus_name in bus_names and bus_names[bus_name] != node_id:
                add_issue(
                    "OPENDSS_SHARED_BUS",
                    "naming",
                    node_type,
                    node_id,
                    f"OpenDSS bus 名称 {bus_name} 被多个对象复用：{bus_names[bus_name]} 与 {node_id}。",
                    "同母线挂载设备可以复用；如果代表不同电气节点，请填写不同的 dss_bus_name。",
                    [],
                    doc="OpenDSS naming",
                    level="warning",
                )
            bus_names[bus_name] = node_id
            element_name = f"{node_type}.{self._safe_name(str(params.get('dss_name') or node_id))}"
            if element_name in element_names and element_names[element_name] != node_id:
                add_issue(
                    "OPENDSS_NAME_COLLISION",
                    "naming",
                    node_type,
                    node_id,
                    f"OpenDSS 元件名 {element_name} 冲突。",
                    "请在对象参数中填写唯一 dss_name。",
                    [],
                    doc="OpenDSS naming",
                )
            element_names[element_name] = node_id

        for edge in edges:
            edge_id = str(edge.get("id") or "")
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            from_id = str(edge.get("from_node_id") or "").strip()
            to_id = str(edge.get("to_node_id") or "").strip()
            if not from_id or not to_id or from_id not in node_map or to_id not in node_map:
                add_issue(
                    "OPENDSS_TOPO_EDGE_ENDPOINT_MISSING",
                    "topology",
                    "line",
                    edge_id,
                    f"线路 {edge_id} 的起点或终点不存在。",
                    "请在拓扑编辑器中重新连接该线路。",
                    ["from_node_id", "to_node_id"],
                    doc="Line bus1/bus2",
                )
                continue
            if from_id == to_id:
                add_issue(
                    "OPENDSS_TOPO_SELF_LOOP_LINE",
                    "topology",
                    "line",
                    edge_id,
                    f"线路 {edge_id} 两端连接到同一对象。",
                    "请删除该自环线路或重新连接不同端点。",
                    ["from_node_id", "to_node_id"],
                    doc="Line bus1/bus2",
                )
            from_node = node_map[from_id]
            to_node = node_map[to_id]
            if self._is_transformer_connection_edge(from_node, to_node):
                continue
            from_bus = self._bus_name(from_node)
            to_bus = self._bus_name(to_node)
            if from_bus == to_bus:
                add_issue(
                    "OPENDSS_LINE_SAME_BUS",
                    "line",
                    "line",
                    edge_id,
                    f"线路 {edge_id} 两端都映射到 OpenDSS 母线 {from_bus}。",
                    "如果这是同母线挂载关系，请删除这条线路；如果是实际电缆/架空线，请把两端节点设置为不同的 dss_bus_name。",
                    ["from_node_id", "to_node_id", "dss_bus_name"],
                    doc="Line bus1/bus2",
                )
                continue
            if not self._has_value(params, "length_km"):
                add_issue("OPENDSS_LINE_LENGTH_REQUIRED", "line", "line", edge_id, f"线路 {edge_id} 缺少长度。", "请在线路参数中填写 length_km。", ["length_km"], doc="Line")
            elif self._num(params.get("length_km"), 0.0) <= 0:
                add_issue("OPENDSS_LINE_LENGTH_NON_POSITIVE", "line", "line", edge_id, f"线路 {edge_id} 长度必须大于 0。", "请在线路参数中填写正数 length_km。", ["length_km"], doc="Line")
            if not self._line_length_unit_is_explicit(params):
                add_issue("OPENDSS_LINE_UNIT_REQUIRED", "line", "line", edge_id, f"线路 {edge_id} 缺少长度单位。", "请在线路参数中填写 units=km。", ["units"], doc="Line")
            if not self._has_value(params, "phases"):
                add_issue("OPENDSS_PHASE_REQUIRED", "line", "line", edge_id, f"线路 {edge_id} 缺少相数。", "请在线路参数中填写 phases。", ["phases"], doc="Line")
            has_linecode = self._has_value(params, "linecode") or self._has_value(params, "line_code")
            has_explicit_rx = self._has_value(params, "r_ohm_per_km") and self._has_value(params, "x_ohm_per_km")
            has_geometry = self._has_value(params, "geometry") or self._has_value(params, "line_geometry")
            if not (has_linecode or has_explicit_rx or has_geometry):
                add_issue(
                    "OPENDSS_LINE_IMPEDANCE_REQUIRED",
                    "line",
                    "line",
                    edge_id,
                    f"线路 {edge_id} 缺少阻抗来源。",
                    "请在线路参数中填写 LineCode，或显式 r/x/c 参数，或填写 Geometry/WireData 来源。",
                    ["linecode 或 r_ohm_per_km/x_ohm_per_km 或 geometry"],
                    doc="LineCode/LineGeometry",
                )
            if has_linecode:
                linecode_name = str(params.get("linecode") or params.get("line_code") or "").strip()
                missing = [
                    field
                    for field in ("r_ohm_per_km", "x_ohm_per_km", "r0_ohm_per_km", "x0_ohm_per_km", "c1_nf_per_km", "c0_nf_per_km")
                    if not self._has_value(params, field) and not self._linecode_library_has(linecode_name, field)
                ]
                if missing:
                    add_issue(
                        "OPENDSS_LINECODE_INCOMPLETE",
                        "line",
                        "line",
                        edge_id,
                        f"线路 {edge_id} 使用 LineCode 但参数不完整。",
                        "请补齐该 LineCode 的 R1/X1/R0/X0/C1/C0 参数，或改用完整显式阻抗。",
                        missing,
                        doc="LineCode",
                    )
            elif has_explicit_rx:
                missing = [field for field in ("r0_ohm_per_km", "x0_ohm_per_km") if not self._has_value(params, field)]
                if missing:
                    add_issue("OPENDSS_LINE_EXPLICIT_RX_INCOMPLETE", "line", "line", edge_id, f"线路 {edge_id} 显式阻抗不完整。", "请补齐 r0_ohm_per_km 和 x0_ohm_per_km。", missing, doc="Line")
            if not (self._has_value(params, "rated_current_a") or self._has_value(params, "normamps")):
                add_issue("OPENDSS_LINE_NORMAMPS_REQUIRED", "line", "line", edge_id, f"线路 {edge_id} 缺少额定载流量。", "请在线路参数中填写 rated_current_a 或 normamps。", ["rated_current_a"], doc="Line")
            if not (self._has_value(params, "emerg_current_a") or self._has_value(params, "emergamps")):
                add_issue("OPENDSS_LINE_EMERGAMPS_REQUIRED", "line", "line", edge_id, f"线路 {edge_id} 缺少应急载流量。", "请在线路参数中填写 emerg_current_a 或 emergamps。", ["emerg_current_a"], doc="Line")

        for node in nodes:
            node_type = str(node.get("type") or "")
            params = self._params(node)
            node_id = str(node.get("id") or "")
            if self._is_transformer_node(node):
                require_fields(
                    node,
                    params,
                    ["rated_kva", "primary_voltage_kv", "voltage_level_kv", "primary_conn", "secondary_conn", "percent_r", "xhl_percent", "phases"],
                    code="OPENDSS_XFMR_WINDING_INCOMPLETE",
                    stage="transformer",
                    object_type=node_type,
                    suggestion="请在变压器参数中补齐容量、电压、接线方式、%R、xhl 和 phases。",
                    doc="Transformer",
                )
                if not (self._has_value(params, "xhl_percent") or self._has_value(params, "xhl")):
                    add_issue("OPENDSS_XFMR_IMPEDANCE_REQUIRED", "transformer", node_type, node_id, f"变压器 {label(node)} 缺少阻抗参数。", "请填写 xhl_percent 或完整阻抗参数。", ["xhl_percent"], doc="Transformer")
            elif node_type == "load":
                require_fields(
                    node,
                    params,
                    ["dss_bus_name", "dss_load_name", "target_kv_ln", "design_kw", "phases"],
                    code="OPENDSS_LOAD_KV_REQUIRED",
                    stage="load",
                    object_type="load",
                    suggestion="请在负荷节点补齐 dss_bus_name、dss_load_name、target_kv_ln、design_kw 和 phases。旧拓扑未保存 model/connection 时按前端默认 model=1、connection=wye 处理。",
                    doc="Load",
                )
                if self._has_value(params, "design_kw") and self._num(params.get("design_kw"), 0.0) <= 0:
                    add_issue("OPENDSS_LOAD_KW_NON_POSITIVE", "load", "load", node_id, f"负荷 {label(node)} 的 design_kw 必须为正值。", "请填写正数 design_kw。", ["design_kw"], doc="Load")
                if not (self._has_value(params, "kvar") or self._has_value(params, "pf") or self._has_value(params, "q_to_p_ratio")):
                    add_issue("OPENDSS_LOAD_REACTIVE_REQUIRED", "load", "load", node_id, f"负荷 {label(node)} 缺少无功或功率因数。", "请填写 kvar、pf 或 q_to_p_ratio，不允许自动使用默认功率因数。", ["kvar 或 pf"], doc="Load")
                if self._bool(params.get("storage_placeholder"), False):
                    add_issue("OPENDSS_STORAGE_EQUIVALENT_NOT_DECLARED", "storage", "load", node_id, f"负荷 {label(node)} 启用了 storage_placeholder。", "请改为显式 storage 节点，或在前端明确声明单等效储能建模方式和完整参数。", ["storage_equivalent_mode"], doc="Storage")
                if isinstance(node.get("runtime_binding"), dict):
                    field_sources["asset_binding"] += 1
                    field_sources["runtime_manifest"] += 1
            elif node_type == "pv":
                require_fields(
                    node,
                    params,
                    ["dss_bus_name", "voltage_level_kv", "pmpp_kw", "kva", "phases"],
                    code="OPENDSS_PV_KVA_REQUIRED",
                    stage="pv",
                    object_type="pv",
                    suggestion="请在光伏节点补齐并网母线、电压、Pmpp、kVA 和 phases。",
                    doc="PVSystem",
                )
                if not (self._has_value(params, "pf") or self._has_value(params, "kvar") or self._has_value(params, "reactive_mode")):
                    add_issue("OPENDSS_PV_REACTIVE_MODE_REQUIRED", "pv", "pv", node_id, f"光伏 {label(node)} 缺少无功模式。", "请填写 pf、kvar 或 reactive_mode。", ["pf 或 kvar 或 reactive_mode"], doc="PVSystem")
                if not (self._has_value(params, "irradiance") or self._has_value(params, "profile_asset_id") or self._has_value(params, "daily_shape")):
                    add_issue("OPENDSS_PV_PROFILE_REQUIRED", "pv", "pv", node_id, f"光伏 {label(node)} 缺少 irradiance 或出力曲线。", "请绑定光伏出力曲线或填写 irradiance。", ["irradiance 或 profile"], doc="PVSystem")
            elif node_type == "storage":
                require_fields(
                    node,
                    params,
                    ["dss_bus_name", "voltage_level_kv", "rated_kw", "rated_kwh", "initial_soc_pct", "reserve_soc_pct", "charge_efficiency_pct", "discharge_efficiency_pct", "phases"],
                    code="OPENDSS_STORAGE_KW_REQUIRED",
                    stage="storage",
                    object_type="storage",
                    suggestion="请在储能节点补齐并网母线、电压、额定功率、容量、SOC、效率和 phases。",
                    doc="Storage",
                )
                if not (self._has_value(params, "pf") or self._has_value(params, "kvar") or self._has_value(params, "reactive_mode")):
                    add_issue("OPENDSS_STORAGE_REACTIVE_MODE_REQUIRED", "storage", "storage", node_id, f"储能 {label(node)} 缺少无功模式。", "请填写 pf、kvar 或 reactive_mode。", ["pf 或 kvar 或 reactive_mode"], doc="Storage")
                if not self._has_value(params, "storage_sign_convention"):
                    add_issue("OPENDSS_STORAGE_SIGN_CONVENTION_REQUIRED", "storage", "storage", node_id, f"储能 {label(node)} 缺少充放电符号约定。", "请在前端明确：优化器正值表示充电还是放电。", ["storage_sign_convention"], doc="Storage")
            elif node_type == "capacitor":
                require_fields(
                    node,
                    params,
                    ["dss_bus_name", "voltage_level_kv", "kvar", "phases", "connection"],
                    code="OPENDSS_CAPACITOR_KVAR_REQUIRED",
                    stage="capacitor",
                    object_type="capacitor",
                    suggestion="请在电容器节点补齐并网母线、电压、kvar、phases 和 connection。",
                    doc="Capacitor",
                )
            elif node_type == "regulator" and self._bool(params.get("enabled"), True):
                require_fields(
                    node,
                    params,
                    ["target_transformer", "winding", "vreg", "band", "ptratio"],
                    code="OPENDSS_REGCONTROL_PARAMS_REQUIRED",
                    stage="control",
                    object_type="regulator",
                    suggestion="请补齐调压控制目标变压器、绕组、vreg、band 和 ptratio。",
                    doc="RegControl",
                )
            elif node_type in {"switch", "breaker", "fuse"}:
                require_fields(
                    node,
                    params,
                    ["target_line"],
                    code="OPENDSS_SWITCH_STATE_NOT_APPLIED",
                    stage="protection",
                    object_type=node_type,
                    suggestion="请在开关/保护设备参数中指定 target_line。",
                    doc="Switch/Fuse/Recloser",
                )
                if str(params.get("protection_model") or "").strip().lower() in {"fuse", "recloser"}:
                    required = ["rated_current_a"] if node_type == "fuse" else ["monitored_term", "switched_term", "shots"]
                    require_fields(
                        node,
                        params,
                        required,
                        code="OPENDSS_FUSE_RECLOSER_PARAMS_REQUIRED",
                        stage="protection",
                        object_type=node_type,
                        suggestion="只有完整保护参数齐全时才生成 Fuse/Recloser；否则仅作为开断设备。",
                        doc="Fuse/Recloser",
                    )

        graph: dict[str, list[str]] = {}
        for edge in edges:
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            if not self._bool(params.get("enabled"), True) or self._bool(params.get("normally_open"), False):
                continue
            a = str(edge.get("from_node_id") or "").strip()
            b = str(edge.get("to_node_id") or "").strip()
            if a in node_map and b in node_map:
                graph.setdefault(a, []).append(b)
                graph.setdefault(b, []).append(a)
        nodes_by_bus: dict[str, list[str]] = {}
        for node in nodes:
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            nodes_by_bus.setdefault(self._bus_name(node), []).append(node_id)
        for same_bus_node_ids in nodes_by_bus.values():
            if len(same_bus_node_ids) < 2:
                continue
            anchor = same_bus_node_ids[0]
            for node_id in same_bus_node_ids[1:]:
                graph.setdefault(anchor, []).append(node_id)
                graph.setdefault(node_id, []).append(anchor)
        reachable: set[str] = set()
        stack = [str(node.get("id")) for node in grid_nodes if node.get("id") is not None]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(nxt for nxt in graph.get(current, []) if nxt not in reachable)
        island_nodes = [str(node.get("id")) for node in nodes if node.get("id") is not None and str(node.get("id")) not in reachable]
        if grid_nodes and island_nodes:
            add_issue(
                "OPENDSS_TOPO_ISLAND_DETECTED",
                "topology",
                "network",
                "",
                f"存在无法追溯到电源的孤岛节点：{', '.join(island_nodes)}。",
                "请检查线路连接、开关状态和常开线路设置。",
                [],
                doc="Circuit connectivity",
            )

        return {
            "project_id": project_id,
            "status": "failed" if any(item["level"] == "error" for item in issues) else "passed",
            "report_dir": str(output_path),
            "input_contract": contract_rows,
            "issues": issues,
            "element_stats": {
                "Vsource": len(grid_nodes),
                "Transformer": sum(1 for node in nodes if self._is_transformer_node(node)),
                "Line": len(edges),
                "Load": sum(1 for node in nodes if str(node.get("type")) == "load"),
                "PVSystem": sum(1 for node in nodes if str(node.get("type")) == "pv"),
                "Storage": sum(1 for node in nodes if str(node.get("type")) == "storage"),
                "Capacitor": sum(1 for node in nodes if str(node.get("type")) == "capacitor"),
                "SwitchProtection": sum(1 for node in nodes if str(node.get("type")) in {"switch", "breaker", "fuse"}),
            },
            "parameter_source_stats": field_sources,
            "official_doc_review": self.OFFICIAL_DOC_REFERENCES,
            "unsupported_capabilities": [
                "WireData/LineGeometry 当前仅做契约校验，完整几何建模需要前端提供导线库和相间坐标后再启用。",
                "Fuse/Recloser 保护配合分析仅在用户显式提供完整保护参数时生成；否则只作为开断状态处理。",
                "多储能逐节点年度优化写入仍需前端声明调度分配方式；未声明时不自动合并。",
            ],
        }

    def _finalize_model_review(
        self,
        review: dict[str, Any],
        artifacts: list[dict[str, Any]],
        structural_checks: dict[str, Any],
        opendss_probe: dict[str, Any],
        output_path: Path,
    ) -> dict[str, Any]:
        redirect_targets = self._master_redirect_targets(output_path / "Master.dss")
        artifact_rows = []
        for item in artifacts:
            rel = str(item.get("relative_path") or "")
            artifact_rows.append(
                {
                    "file": rel,
                    "path": item.get("absolute_path"),
                    "exists": bool(item.get("exists")),
                    "redirected_by_master": rel in redirect_targets,
                    "sha256": item.get("sha256"),
                }
            )
        review["dss_files"] = artifact_rows
        review["master_redirects"] = sorted(redirect_targets)
        review["structural_checks"] = structural_checks
        review["opendss_probe"] = opendss_probe
        if structural_checks.get("errors"):
            review["status"] = "failed"
        if str(opendss_probe.get("status") or "").lower() == "failed":
            review["status"] = "failed"
        return review

    def _render_model_review_markdown(self, review: dict[str, Any]) -> str:
        lines = [
            "# OpenDSS 建模审查报告",
            "",
            f"- 项目：{review.get('project_id')}",
            f"- 结论：{review.get('status')}",
            f"- error 数：{sum(1 for item in review.get('issues') or [] if item.get('level') == 'error')}",
            "",
            "## 元件统计",
        ]
        for key, value in (review.get("element_stats") or {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## 问题清单"])
        issues = review.get("issues") or []
        if not issues:
            lines.append("- 无")
        for item in issues:
            lines.append(
                f"- [{item.get('level')}] {item.get('code')} | {item.get('object_type')} {item.get('object_id')} | {item.get('message')}"
            )
        lines.extend(["", "## DSS 文件"])
        for item in review.get("dss_files") or []:
            lines.append(f"- {item.get('file')} | redirected={item.get('redirected_by_master')} | sha256={item.get('sha256')}")
        lines.extend(["", "## 官方文档核查"])
        for item in review.get("official_doc_review") or []:
            lines.append(f"- {item.get('objects')}: {item.get('url')}；确认：{item.get('confirmed')}")
        probe = review.get("opendss_probe") or {}
        lines.extend(
            [
                "",
                "## Compile / Solve 探针",
                f"- status: {probe.get('status')}",
                f"- compile_succeeded: {probe.get('compile_succeeded')}",
                f"- solve_converged: {probe.get('solve_converged')}",
                f"- message: {probe.get('message')}",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _sha256_text(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _master_redirect_targets(master_path: Path) -> set[str]:
        if not master_path.exists():
            return set()
        targets: set[str] = set()
        for line in master_path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text.lower().startswith("redirect "):
                continue
            target = text.split(None, 1)[1].strip().strip('"[]')
            if target:
                targets.add(Path(target).name)
        return targets

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
            "voltage_min_pu": None,
            "voltage_max_pu": None,
            "max_line_loading_pct": None,
            "total_losses_kw": None,
            "total_losses_kvar": None,
            "source_power_kw": None,
            "source_power_kvar": None,
            "compile_result": "",
            "solve_result": "",
            "message": "",
            "stderr_tail": "",
        }
        if not master_path.exists():
            probe["message"] = f"Master.dss 不存在：{master_path}"
            return probe

        script = self._opendss_probe_script()

        probe_timeout_seconds = 30
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
                timeout=probe_timeout_seconds,
                env=probe_env,
            )
        except subprocess.TimeoutExpired:
            probe["attempted"] = True
            probe["status"] = "failed"
            probe["message"] = (
                f"OpenDSS probe 超时（{probe_timeout_seconds} 秒）："
                "COM 引擎未在限定时间内完成 Compile/Solve，已阻止求解放行。"
            )
            return probe
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

    @staticmethod
    def _blocked_opendss_probe(message: str) -> dict[str, Any]:
        return {
            "mode": "blocked_by_model_review",
            "attempted": False,
            "status": "blocked",
            "engine": "OpenDSS COM",
            "compile_succeeded": False,
            "solve_executed": False,
            "solve_converged": False,
            "circuit_name": "",
            "bus_count": 0,
            "line_count": 0,
            "load_count": 0,
            "voltage_min_pu": None,
            "voltage_max_pu": None,
            "max_line_loading_pct": None,
            "total_losses_kw": None,
            "total_losses_kvar": None,
            "source_power_kw": None,
            "source_power_kvar": None,
            "compile_result": "",
            "solve_result": "",
            "message": message,
            "stderr_tail": "",
        }

    @staticmethod
    def _opendss_probe_script() -> str:
        return """
import json
import sys

if sys.platform.startswith("win"):
    try:
        import ctypes

        SEM_FAILCRITICALERRORS = 0x0001
        SEM_NOGPFAULTERRORBOX = 0x0002
        SEM_NOOPENFILEERRORBOX = 0x8000
        ctypes.windll.kernel32.SetErrorMode(
            SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX
        )
    except Exception:
        pass

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
    "voltage_min_pu": None,
    "voltage_max_pu": None,
    "max_line_loading_pct": None,
    "total_losses_kw": None,
    "total_losses_kvar": None,
    "source_power_kw": None,
    "source_power_kvar": None,
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

        try:
            voltage_values = []
            for bus_name in list(circuit.AllBusNames):
                try:
                    circuit.SetActiveBus(str(bus_name))
                    raw = list(circuit.ActiveBus.puVmagAngle)
                    voltage_values.extend(float(raw[i]) for i in range(0, len(raw), 2) if float(raw[i]) > 0)
                except Exception:
                    continue
            if voltage_values:
                result["voltage_min_pu"] = min(voltage_values)
                result["voltage_max_pu"] = max(voltage_values)
        except Exception:
            pass

        try:
            loading_values = []
            line_cursor = circuit.Lines.First
            while line_cursor:
                normamps = float(getattr(circuit.Lines, "NormAmps", 0.0) or 0.0)
                active = circuit.ActiveCktElement
                raw = list(getattr(active, "CurrentsMagAng", []) or [])
                current_values = [float(raw[i]) for i in range(0, len(raw), 2)]
                if normamps > 0 and current_values:
                    loading_values.append(max(current_values) / normamps * 100.0)
                line_cursor = circuit.Lines.Next
            if loading_values:
                result["max_line_loading_pct"] = max(loading_values)
        except Exception:
            pass

        try:
            losses = list(circuit.Losses)
            if len(losses) >= 2:
                result["total_losses_kw"] = float(losses[0]) / 1000.0
                result["total_losses_kvar"] = float(losses[1]) / 1000.0
        except Exception:
            pass

        try:
            total_power = list(circuit.TotalPower)
            if len(total_power) >= 2:
                result["source_power_kw"] = float(total_power[0])
                result["source_power_kvar"] = float(total_power[1])
        except Exception:
            pass

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
        model_review: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        errors: list[str] = []
        check_warnings: list[str] = []

        review_errors = [
            item
            for item in (model_review or {}).get("issues", [])
            if isinstance(item, dict) and item.get("level") == "error"
        ]
        self._append_check(
            checks,
            name="opendss_model_review_errors",
            passed=not review_errors,
            detail=(
                "OpenDSS 建模输入契约审查未发现 error。"
                if not review_errors
                else f"OpenDSS 建模输入契约审查发现 {len(review_errors)} 个 error。"
            ),
        )
        for item in review_errors:
            code = str(item.get("code") or "OPENDSS_MODEL_REVIEW_ERROR")
            object_type = str(item.get("object_type") or "")
            object_id = str(item.get("object_id") or "")
            message = str(item.get("message") or "").strip()
            suggestion = str(item.get("suggestion") or "").strip()
            target = f"{object_type} {object_id}".strip()
            suffix = f" 建议：{suggestion}" if suggestion else ""
            errors.append(f"{code}: {target} {message}{suffix}".strip())

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
        checks.append(
            {
                "name": "bus_names_unique_or_shared",
                "status": "pass" if not duplicate_buses else "warn",
                "detail": (
                    "母线命名唯一。"
                    if not duplicate_buses
                    else f"多个可视化节点映射到同一 OpenDSS 母线：{', '.join(duplicate_buses)}。如为同母线挂载设备可忽略，否则请修正。"
                ),
            }
        )
        if duplicate_buses:
            check_warnings.append(
                f"多个可视化节点映射到同一 OpenDSS 母线：{', '.join(duplicate_buses)}，请确认这不是误填。"
            )

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
        return self._num(params.get("voltage_level_kv"), 0.0)

    def _source_voltage_kv(self, node: dict[str, Any] | None, phases: int) -> float:
        params = self._params(node or {})
        raw = params.get("base_kv")
        if raw in (None, ""):
            return 0.0
        kv = self._num(raw, 0.0)
        if int(phases) > 1:
            kv = self._line_line_kv_from_possible_line_neutral(kv)
        return kv

    def _load_voltage_kv_for_opendss(self, params: dict[str, Any], phases: int) -> float:
        raw = params.get("target_kv_ln")
        return self._distribution_voltage_kv_for_opendss(raw, phases)

    def _distribution_voltage_kv_for_opendss(self, value: Any, phases: int) -> float:
        kv = self._num(value, 0.0)
        if int(phases) > 1:
            kv = self._line_line_kv_from_possible_line_neutral(kv)
        return kv

    @classmethod
    def _line_line_kv_from_possible_line_neutral(cls, kv: float) -> float:
        if kv <= 0:
            return kv
        for nominal_ll in cls.COMMON_LINE_LINE_KV:
            nominal_ln = nominal_ll / math.sqrt(3.0)
            if abs(kv - nominal_ln) <= max(0.002, nominal_ln * 0.03):
                return float(nominal_ll)
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
            return self._num(params.get("rated_kw"), self._num(params.get("rated_power_kw"), 0.0))
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
        out: list[float] = []
        for value in values:
            if value <= 0:
                continue
            if not any(abs(value - existing) <= max(0.001, existing * 0.001) for existing in out):
                out.append(float(value))
        return out

    def _safe_name(self, raw: str) -> str:
        out = []
        for ch in raw:
            if ch.isascii() and (ch.isalnum() or ch == "_"):
                out.append(ch)
            else:
                out.append("_")
        return "".join(out).strip("_") or "unnamed"

    def _topology_phases(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> int:
        values: list[int] = []
        for node in nodes:
            params = self._params(node)
            if self._has_value(params, "phases"):
                values.append(int(self._num(params.get("phases"), 0)))
        for edge in edges:
            params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
            if self._has_value(params, "phases"):
                values.append(int(self._num(params.get("phases"), 0)))
        positives = [value for value in values if value in {1, 2, 3}]
        return positives[0] if positives else 3

    def _node_phases(self, node: dict[str, Any] | None, default: int = 3) -> int:
        if node is None:
            return int(default)
        params = self._params(node)
        if self._has_value(params, "phases"):
            phases = int(self._num(params.get("phases"), default))
            return phases if phases in {1, 2, 3} else int(default)
        return int(default)

    def _edge_phases(self, edge: dict[str, Any], from_node: dict[str, Any], to_node: dict[str, Any]) -> int:
        params = edge.get("params") if isinstance(edge.get("params"), dict) else {}
        if self._has_value(params, "phases"):
            phases = int(self._num(params.get("phases"), 3))
            return phases if phases in {1, 2, 3} else 3
        return min(self._node_phases(from_node, 3), self._node_phases(to_node, 3), 3)

    def _phase_suffix(self, phases: int) -> str:
        phase_count = int(phases) if int(phases) in {1, 2, 3} else 3
        return "." + ".".join(str(i) for i in range(1, phase_count + 1))

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
        if not text:
            return ""
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

    @staticmethod
    def _has_value(params: dict[str, Any], key: str) -> bool:
        value = params.get(key)
        if value in (None, ""):
            return False
        if isinstance(value, float) and math.isnan(value):
            return False
        return True
