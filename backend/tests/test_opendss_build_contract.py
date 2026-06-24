from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.build_export_service import BuildExportService  # noqa: E402
from services.dss_builder_service import DssBuilderService  # noqa: E402
from services.solver_execution_service import SolverExecutionService  # noqa: E402


def _project(topology: dict) -> dict:
    return {
        "project_id": "proj01",
        "project_name": "OpenDSS contract",
        "network": topology,
    }


def test_read_build_manifest_does_not_generate_missing_manifest(tmp_path):
    service = BuildExportService(data_root=tmp_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        service.read_build_manifest("proj01")

    assert "请先执行构建" in str(exc_info.value)
    assert not (tmp_path / "proj01" / "build" / "manifest" / "build_manifest.json").exists()


def test_stale_manifest_marks_workspace_not_ready(tmp_path):
    service = BuildExportService(data_root=tmp_path)
    project_dir = tmp_path / "proj01"
    manifest_dir = project_dir / "build" / "manifest"
    manifest_dir.mkdir(parents=True)

    old_topology = {"nodes": [], "edges": [], "economic_parameters": {}}
    new_topology = {
        "nodes": [{"id": "grid_001", "type": "grid", "name": "grid", "params": {"base_kv": 110}}],
        "edges": [],
        "economic_parameters": {},
    }
    (project_dir / "project.json").write_text(json.dumps(_project(new_topology), ensure_ascii=False), encoding="utf-8")
    (manifest_dir / "build_manifest.json").write_text(
        json.dumps(
            {
                "success": True,
                "project_id": "proj01",
                "topology_hash": service._topology_hash(old_topology),
                "warnings": [],
                "errors": [],
                "ready_for_solver": True,
                "build_gate": {"ready_for_solver_gate": True, "warnings": [], "errors": []},
                "solver_handoff": {"status": "ready", "warnings": [], "errors": []},
                "solver_workspace": {"ready_for_solver": True, "warnings": [], "errors": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = service.read_build_manifest("proj01")

    assert manifest["manifest_stale"] is True
    assert manifest["ready_for_solver"] is False
    assert manifest["build_gate"]["ready_for_solver_gate"] is False
    assert manifest["solver_handoff"]["status"] == "blocked"
    assert manifest["solver_workspace"]["ready_for_solver"] is False
    assert any("已过期" in item for item in manifest["warnings"])


def test_build_input_change_marks_manifest_stale_even_when_topology_matches(tmp_path):
    service = BuildExportService(data_root=tmp_path)
    project_dir = tmp_path / "proj01"
    manifest_dir = project_dir / "build" / "manifest"
    manifest_dir.mkdir(parents=True)
    topology = {
        "nodes": [{"id": "grid_001", "type": "grid", "name": "grid", "params": {"base_kv": 110}}],
        "edges": [],
        "economic_parameters": {},
    }
    old_project = _project(topology)
    old_project["tariff"] = {
        "asset": {
            "file_id": "tariff-old",
            "file_name": "old.xlsx",
            "metadata": {"stored_path": "old.xlsx"},
        }
    }
    new_project = _project(topology)
    new_project["tariff"] = {
        "asset": {
            "file_id": "tariff-new",
            "file_name": "new.xlsx",
            "metadata": {"stored_path": "new.xlsx"},
        }
    }
    (project_dir / "project.json").write_text(json.dumps(new_project, ensure_ascii=False), encoding="utf-8")
    (manifest_dir / "build_manifest.json").write_text(
        json.dumps(
            {
                "success": True,
                "project_id": "proj01",
                "topology_hash": service._topology_hash(topology),
                "build_input_hash": service._build_input_hash(old_project),
                "warnings": [],
                "errors": [],
                "ready_for_solver": True,
                "build_gate": {"ready_for_solver_gate": True, "warnings": [], "errors": []},
                "solver_handoff": {"status": "ready", "warnings": [], "errors": []},
                "solver_workspace": {"ready_for_solver": True, "warnings": [], "errors": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest = service.read_build_manifest("proj01")

    assert manifest["manifest_stale"] is True
    assert manifest["ready_for_solver"] is False
    assert manifest["solver_workspace"]["ready_for_solver"] is False


def test_run_solver_missing_manifest_reports_missing_build(tmp_path):
    service = SolverExecutionService(data_root=tmp_path)
    (tmp_path / "proj01").mkdir()

    with pytest.raises(FileNotFoundError) as exc_info:
        service.run_solver("proj01")

    assert "未找到 build manifest" in str(exc_info.value)


def test_run_solver_rejects_stale_build_input_hash(tmp_path):
    build_service = BuildExportService(data_root=tmp_path)
    solver_service = SolverExecutionService(data_root=tmp_path)
    project_dir = tmp_path / "proj01"
    manifest_dir = project_dir / "build" / "manifest"
    manifest_dir.mkdir(parents=True)
    topology = {"nodes": [], "edges": [], "economic_parameters": {}}
    old_project = _project(topology)
    old_project["solve_config"] = {"extra": {"population_size": 16}}
    new_project = _project(topology)
    new_project["solve_config"] = {"extra": {"population_size": 32}}
    (project_dir / "project.json").write_text(json.dumps(new_project, ensure_ascii=False), encoding="utf-8")
    (manifest_dir / "build_manifest.json").write_text(
        json.dumps(
            {
                "success": True,
                "project_id": "proj01",
                "topology_hash": build_service._topology_hash(topology),
                "build_input_hash": build_service._build_input_hash(old_project),
                "solver_workspace": {"ready_for_solver": True, "workspace_dir": str(project_dir / "build" / "solver_workspace")},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        solver_service.run_solver("proj01")

    assert "build manifest 已过期" in str(exc_info.value)


def test_run_solver_rejects_manifest_when_build_gate_is_not_ready(tmp_path):
    build_service = BuildExportService(data_root=tmp_path)
    solver_service = SolverExecutionService(data_root=tmp_path)
    project_dir = tmp_path / "proj01"
    workspace_dir = project_dir / "build" / "solver_workspace"
    manifest_dir = project_dir / "build" / "manifest"
    workspace_dir.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    topology = {"nodes": [], "edges": [], "economic_parameters": {}}
    project = _project(topology)
    (project_dir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    (manifest_dir / "build_manifest.json").write_text(
        json.dumps(
            {
                "success": True,
                "project_id": "proj01",
                "topology_hash": build_service._topology_hash(topology),
                "build_input_hash": build_service._build_input_hash(project),
                "ready_for_solver": True,
                "build_gate": {
                    "ready_for_solver_gate": False,
                    "errors": ["OpenDSS probe 未通过"],
                    "warnings": [],
                },
                "solver_workspace": {
                    "ready_for_solver": True,
                    "workspace_dir": str(workspace_dir),
                    "errors": [],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        solver_service.run_solver("proj01")

    assert "solver workspace 尚未就绪" in str(exc_info.value)
    assert "OpenDSS probe 未通过" in str(exc_info.value)


def test_generate_build_rejects_invalid_preview_without_writing_manifest(tmp_path):
    service = BuildExportService(data_root=tmp_path)
    project_dir = tmp_path / "proj01"
    project_dir.mkdir()
    (project_dir / "project.json").write_text(
        json.dumps(_project({"nodes": [], "edges": [], "economic_parameters": {}}), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        service.generate_build("proj01")

    assert "拓扑预览校验未通过" in str(exc_info.value)
    assert not (project_dir / "build" / "manifest" / "build_manifest.json").exists()


def test_build_gate_requires_real_opendss_probe_pass():
    service = BuildExportService(data_root="unused")
    preview = {"summary": {"ready_for_build": True, "warnings": [], "errors": []}}
    payload = {
        "dss_compile_summary": {
            "structural_checks": {"passed": True, "warnings": [], "errors": []},
            "opendss_probe": {
                "status": "skipped",
                "compile_succeeded": False,
                "solve_converged": False,
                "message": "win32com is unavailable",
            },
        }
    }

    gate = service._build_gate_status(preview, payload)

    assert gate["ready_for_solver_gate"] is False
    assert gate["opendss_probe_passed"] is False
    assert any("win32com" in item for item in gate["errors"])

    payload["dss_compile_summary"]["opendss_probe"] = {
        "status": "passed",
        "compile_succeeded": True,
        "solve_converged": True,
        "message": "ok",
    }
    gate = service._build_gate_status(preview, payload)
    assert gate["ready_for_solver_gate"] is True


def test_opendss_probe_script_suppresses_windows_crash_dialogs():
    script = DssBuilderService._opendss_probe_script()

    compile(script, "<opendss_probe>", "exec")

    assert "SetErrorMode" in script
    assert "SEM_NOGPFAULTERRORBOX" in script
    assert script.index("SetErrorMode") < script.index("win32com.client")


def test_opendss_probe_timeout_message_does_not_leak_inline_script(tmp_path, monkeypatch):
    master_path = tmp_path / "Master.dss"
    master_path.write_text("Clear\n", encoding="utf-8")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", fake_run)

    probe = DssBuilderService()._probe_opendss_compile(master_path)

    assert probe["attempted"] is True
    assert probe["status"] == "failed"
    assert "OpenDSS probe 超时" in probe["message"]
    assert "win32com.client" not in probe["message"]
    assert "python.exe" not in probe["message"]


def test_line_count_summary_uses_explicit_label_for_empty_linecode():
    builder = DssBuilderService()

    counts = builder._count_by_key(
        [{"linecode": ""}, {"linecode": "LC_MAIN"}, {"linecode": "LC_MAIN"}],
        "linecode",
        empty_label="EXPLICIT_IMPEDANCE",
    )

    assert counts == {"EXPLICIT_IMPEDANCE": 1, "LC_MAIN": 2}


def test_model_review_blocks_missing_line_impedance_and_writes_reports(tmp_path, monkeypatch):
    builder = DssBuilderService()

    def fail_probe(_master_path):
        raise AssertionError("probe should be blocked before OpenDSS COM is invoked")

    monkeypatch.setattr(builder, "_probe_opendss_compile", fail_probe)

    topology = {
        "nodes": [
            {
                "id": "grid_001",
                "type": "grid",
                "name": "grid",
                "params": {
                    "source_bus": "sourcebus",
                    "base_kv": 110,
                    "pu": 1.0,
                    "phases": 3,
                    "mvasc3": 500,
                    "mvasc1": 250,
                    "x1r1": 10,
                    "x0r0": 10,
                },
            },
            {
                "id": "tx_001",
                "type": "transformer",
                "name": "tx",
                "params": {
                    "dss_bus_name": "n0",
                    "rated_kva": 1000,
                    "primary_voltage_kv": 110,
                    "voltage_level_kv": 10,
                    "primary_conn": "delta",
                    "secondary_conn": "wye",
                    "percent_r": 0.5,
                    "xhl_percent": 6.0,
                    "phases": 3,
                },
            },
            {
                "id": "load_001",
                "type": "load",
                "name": "load",
                "params": {
                    "dss_bus_name": "n1",
                    "dss_load_name": "LD01",
                    "target_kv_ln": 10,
                    "design_kw": 100,
                    "model": 1,
                    "connection": "wye",
                    "phases": 3,
                    "pf": 0.95,
                },
            },
        ],
        "edges": [
            {
                "id": "edge_grid_tx",
                "from_node_id": "grid_001",
                "to_node_id": "tx_001",
                "params": {"enabled": True},
            },
            {
                "id": "edge_tx_load",
                "from_node_id": "tx_001",
                "to_node_id": "load_001",
                "params": {
                    "length_km": 1.0,
                    "units": "km",
                    "phases": 3,
                    "rated_current_a": 100,
                    "emerg_current_a": 120,
                },
            },
        ],
    }

    payload = builder.compile_topology("proj01", topology, tmp_path)
    summary = payload["dss_compile_summary"]
    review = json.loads((tmp_path / "opendss_model_review.json").read_text(encoding="utf-8"))

    assert summary["opendss_probe"]["status"] == "blocked"
    assert summary["structural_checks"]["passed"] is False
    assert any("OPENDSS_LINE_IMPEDANCE_REQUIRED" in item for item in summary["errors"])
    assert any(item["code"] == "OPENDSS_LINE_IMPEDANCE_REQUIRED" for item in review["issues"])
    assert (tmp_path / "opendss_model_review.md").exists()
    assert "LC_MAIN" not in (tmp_path / "LineCodes_Custom.dss").read_text(encoding="utf-8")


def test_length_km_and_selected_frontend_linecode_are_sufficient_for_line_units_and_library_fields():
    service = BuildExportService(data_root="unused")
    topology = {
        "nodes": [
            {
                "id": "grid_001",
                "type": "grid",
                "name": "grid",
                "params": {"source_bus": "sourcebus", "base_kv": 110, "phases": 3},
            },
            {
                "id": "tx_001",
                "type": "transformer",
                "name": "tx",
                "params": {"rated_kva": 1000, "phases": 3},
            },
            {
                "id": "load_001",
                "type": "load",
                "name": "load",
                "params": {
                    "node_id": 1,
                    "target_kv_ln": 10,
                    "dss_bus_name": "n1",
                    "dss_load_name": "LD01",
                    "design_kw": 100,
                    "phases": 3,
                },
            },
        ],
        "edges": [
            {
                "id": "edge_grid_tx",
                "from_node_id": "grid_001",
                "to_node_id": "tx_001",
                "params": {"enabled": True},
            },
            {
                "id": "edge_tx_load",
                "from_node_id": "tx_001",
                "to_node_id": "load_001",
                "params": {
                    "length_km": 0.005,
                    "linecode": "LC_CABLE",
                    "r_ohm_per_km": 0.254261364,
                    "x_ohm_per_km": 0.097045455,
                    "rated_current_a": 400,
                    "emerg_current_a": 500,
                    "phases": 3,
                    "enabled": True,
                },
            },
        ],
        "economic_parameters": {},
    }

    validation = service._validate_topology(topology)
    assert not any("缺少长度单位" in item for item in validation["errors"])
    assert not any("LineCode 参数不完整" in item for item in validation["errors"])

    builder = DssBuilderService()
    node_map = {str(node["id"]): node for node in topology["nodes"]}
    review = builder._build_model_review("proj01", topology["nodes"], topology["edges"], node_map, Path("unused"))
    issue_messages = [str(item.get("message") or "") for item in review["issues"]]
    assert not any("缺少长度单位" in item for item in issue_messages)
    assert not any("LineCode 但参数不完整" in item for item in issue_messages)


def _runtime_capacity_validation_case(tmp_path: Path, *, category: str = "residential") -> tuple[dict, dict]:
    runtime_dir = tmp_path / "proj01" / "assets" / "runtime" / "load_001"
    runtime_dir.mkdir(parents=True)
    year_map = runtime_dir / "runtime_year_model_map.csv"
    model_library = runtime_dir / "runtime_model_library.csv"
    year_map.write_text("internal_model_id\nm1\n", encoding="utf-8")
    hour_columns = ",".join(f"h{i:02d}" for i in range(24))
    hour_values = ",".join("120" if i == 18 else "40" for i in range(24))
    model_library.write_text(f"internal_model_id,{hour_columns}\nm1,{hour_values}\n", encoding="utf-8")

    topology = {
        "nodes": [
            {"id": "grid", "type": "grid", "name": "grid", "params": {"source_bus": "sourcebus", "base_kv": 110, "phases": 3}},
            {
                "id": "tx_main",
                "type": "transformer",
                "name": "main tx",
                "params": {"rated_kva": 10000, "primary_voltage_kv": 110, "voltage_level_kv": 10, "phases": 3},
            },
            {
                "id": "user_tx",
                "type": "transformer",
                "name": "user tx",
                "params": {
                    "transformer_role": "distribution",
                    "is_distribution_transformer": True,
                    "rated_kva": 80,
                    "primary_voltage_kv": 10,
                    "voltage_level_kv": 0.4,
                    "phases": 3,
                },
            },
            {
                "id": "load_001",
                "type": "load",
                "name": "LD01",
                "params": {
                    "node_id": 1,
                    "dss_bus_name": "n1_load",
                    "dss_load_name": "LD01",
                    "target_kv_ln": 0.4,
                    "category": category,
                    "design_kw": 50,
                    "q_to_p_ratio": 0.2,
                    "transformer_capacity_kva": 100,
                    "transformer_pf_limit": 0.95,
                    "transformer_reserve_ratio": 0.15,
                    "phases": 3,
                },
                "runtime_binding": {
                    "year_map_file_id": "year_asset",
                    "model_library_file_id": "model_asset",
                },
            },
        ],
        "edges": [
            {"id": "edge_grid_tx", "from_node_id": "grid", "to_node_id": "tx_main", "params": {"enabled": True}},
            {
                "id": "edge_main_user_tx",
                "from_node_id": "tx_main",
                "to_node_id": "user_tx",
                "params": {"length_km": 0.1, "units": "km", "linecode": "LC_MAIN", "phases": 3, "rated_current_a": 1000, "emerg_current_a": 1200},
            },
            {
                "id": "edge_tx_load",
                "from_node_id": "user_tx",
                "to_node_id": "load_001",
                "params": {"length_km": 0.005, "units": "km", "linecode": "LC_CABLE", "phases": 3, "rated_current_a": 300, "emerg_current_a": 360},
            },
        ],
        "economic_parameters": {},
    }
    project = {
        "project_id": "proj01",
        "network": topology,
        "assets": {
            "year_asset": {"metadata": {"stored_path": str(year_map)}},
            "model_asset": {"metadata": {"stored_path": str(model_library)}},
        },
    }
    return topology, project


def test_build_preview_warns_residential_capacity_recommendation(tmp_path):
    topology, project = _runtime_capacity_validation_case(tmp_path, category="residential")
    validation = BuildExportService(data_root=tmp_path)._validate_topology(topology, project)

    warnings = "\n".join(validation["warnings"])
    assert "导入曲线峰值 120.0 kW 高于设计负荷" not in warnings
    assert "transformer_capacity_kva=100.0 kVA 与相连用户配变 user tx rated_kva=80.0 kVA 不一致" in warnings
    assert "居民负荷节点 LD01 当前相连/配置配变容量 80.0 kVA" in warnings
    assert "建议容量不低于 160 kVA" in warnings
    assert "超过配变运行可用上限" not in warnings


def test_build_preview_suppresses_inference_warnings_for_industrial_known_capacity(tmp_path):
    topology, project = _runtime_capacity_validation_case(tmp_path, category="industrial")
    validation = BuildExportService(data_root=tmp_path)._validate_topology(topology, project)

    warnings = "\n".join(validation["warnings"])
    assert "导入曲线峰值 120.0 kW 高于设计负荷" not in warnings
    assert "transformer_capacity_kva=100.0 kVA 与相连用户配变" not in warnings
    assert "建议容量不低于" not in warnings


def test_legacy_loads_without_connection_and_model_use_frontend_defaults(tmp_path, monkeypatch):
    builder = DssBuilderService()
    topology_path = Path("backend/data/topology_templates/403a70db9fe2.json")
    topology = json.loads(topology_path.read_text(encoding="utf-8"))["topology"]

    def blocked_probe(_master_path):
        return DssBuilderService._blocked_opendss_probe("unit test")

    monkeypatch.setattr(builder, "_probe_opendss_compile", blocked_probe)

    node_map = {str(node["id"]): node for node in topology["nodes"]}
    review = builder._build_model_review("proj01", topology["nodes"], topology["edges"], node_map, tmp_path)
    issue_text = "\n".join(str(item.get("message") or "") for item in review["issues"])
    assert "缺少 OpenDSS 建模字段：model, connection" not in issue_text

    payload = builder.compile_topology("proj01", topology, tmp_path)
    assert payload["dss_compile_summary"]["structural_checks"]["passed"] is True
    loads_text = (tmp_path / "Loads_Runtime.dss").read_text(encoding="utf-8")
    assert "conn=wye" in loads_text
    assert "Model=1" in loads_text


def test_duplicate_bus_mapping_is_warning_not_structural_error():
    builder = DssBuilderService()
    artifacts = [
        {"relative_path": name}
        for name in {
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
    ]
    nodes = [
        {"id": "grid_001", "type": "grid", "name": "grid", "params": {"source_bus": "sourcebus"}},
        {"id": "tx_001", "type": "transformer", "name": "tx", "params": {"dss_bus_name": "n0"}},
        {"id": "load_001", "type": "load", "name": "load", "params": {"node_id": 1}},
        {"id": "pv_001", "type": "pv", "name": "pv", "params": {"dss_bus_name": "n1"}},
    ]
    bus_map = builder._build_bus_map(nodes)

    checks = builder._build_structural_checks(
        nodes=nodes,
        edges=[],
        node_map={str(node["id"]): node for node in nodes},
        artifacts=artifacts,
        bus_map=bus_map,
        line_summary=[],
        topology_case_summary={
            "editable_line_ids": [],
            "invalid_endpoint_edge_ids": [],
            "skipped_transformer_connection_edge_count": 0,
        },
        warnings=[],
    )

    assert checks["passed"] is True
    assert any("同一 OpenDSS 母线" in item for item in checks["warnings"])
    assert not checks["errors"]


def test_common_line_neutral_voltage_inputs_are_normalized_to_line_line_voltage():
    builder = DssBuilderService()
    build_service = BuildExportService(data_root="unused")
    solver = SolverExecutionService(data_root="unused")

    low_voltage_ln = 0.4 / 3 ** 0.5
    medium_voltage_ln = 10.0 / 3 ** 0.5

    assert builder._distribution_voltage_kv_for_opendss(low_voltage_ln, 3) == pytest.approx(0.4)
    assert builder._distribution_voltage_kv_for_opendss(low_voltage_ln, 1) == pytest.approx(low_voltage_ln)
    assert builder._distribution_voltage_kv_for_opendss(medium_voltage_ln, 3) == pytest.approx(10.0)
    assert build_service._normalize_distribution_base_kv(low_voltage_ln, 3) == pytest.approx(0.4)
    assert solver._estimate_line_line_voltage_kv(0.4) == pytest.approx(0.4)
    assert solver._estimate_line_line_voltage_kv(low_voltage_ln) == pytest.approx(0.4)
    assert solver._estimate_line_line_voltage_kv(medium_voltage_ln) == pytest.approx(10.0)


def test_shared_bus_devices_are_allowed_without_visual_line(tmp_path):
    builder = DssBuilderService()
    service = BuildExportService(data_root="unused")
    nodes = [
        {
            "id": "grid_001",
            "type": "grid",
            "name": "grid",
            "params": {
                "source_bus": "sourcebus",
                "base_kv": 110,
                "pu": 1,
                "phases": 3,
                "mvasc3": 500,
                "mvasc1": 250,
                "x1r1": 10,
                "x0r0": 10,
            },
        },
        {
            "id": "tx_001",
            "type": "transformer",
            "name": "tx",
            "params": {
                "dss_bus_name": "n0",
                "rated_kva": 1000,
                "primary_voltage_kv": 110,
                "voltage_level_kv": 10,
                "primary_conn": "wye",
                "secondary_conn": "wye",
                "percent_r": 0.5,
                "xhl_percent": 6.0,
                "phases": 3,
            },
        },
        {"id": "bus_001", "type": "bus", "name": "bus", "params": {"dss_bus_name": "n1", "voltage_level_kv": 10, "phases": 3}},
        {
            "id": "load_001",
            "type": "load",
            "name": "load",
            "params": {
                "dss_bus_name": "n1",
                "dss_load_name": "LD01",
                "target_kv_ln": 10,
                "design_kw": 100,
                "q_to_p_ratio": 0.25,
                "phases": 3,
            },
        },
        {
            "id": "pv_001",
            "type": "pv",
            "name": "pv",
            "params": {
                "dss_bus_name": "n1",
                "voltage_level_kv": 10,
                "pmpp_kw": 20,
                "kva": 25,
                "pf": 1,
                "irradiance": 1,
                "phases": 3,
            },
        },
    ]
    edges = [
        {"id": "edge_grid_tx", "from_node_id": "grid_001", "to_node_id": "tx_001", "params": {"enabled": True}},
        {
            "id": "edge_tx_bus",
            "from_node_id": "tx_001",
            "to_node_id": "bus_001",
            "params": {
                "length_km": 1.0,
                "linecode": "LC_MAIN",
                "phases": 3,
                "rated_current_a": 100,
                "emerg_current_a": 120,
                "enabled": True,
            },
        },
    ]
    topology = {"nodes": nodes, "edges": edges, "economic_parameters": {}}

    validation = service._validate_topology(topology)
    assert not validation["errors"]

    review = builder._build_model_review("proj01", nodes, edges, {str(node["id"]): node for node in nodes}, tmp_path)
    assert not [item for item in review["issues"] if item["level"] == "error"]
    assert any(item["code"] == "OPENDSS_SHARED_BUS" and item["level"] == "warning" for item in review["issues"])


def test_same_bus_visual_line_is_blocked_by_build_validation(tmp_path):
    builder = DssBuilderService()
    service = BuildExportService(data_root="unused")
    topology = {
        "nodes": [
            {"id": "grid_001", "type": "grid", "name": "grid", "params": {"source_bus": "sourcebus", "base_kv": 110, "phases": 3}},
            {"id": "tx_001", "type": "transformer", "name": "tx", "params": {"dss_bus_name": "n0", "rated_kva": 1000, "phases": 3}},
            {"id": "bus_001", "type": "bus", "name": "bus", "params": {"dss_bus_name": "n1", "voltage_level_kv": 10, "phases": 3}},
            {
                "id": "load_001",
                "type": "load",
                "name": "load",
                "params": {"dss_bus_name": "n1", "dss_load_name": "LD01", "target_kv_ln": 10, "design_kw": 100, "q_to_p_ratio": 0.25, "phases": 3},
            },
        ],
        "edges": [
            {"id": "edge_grid_tx", "from_node_id": "grid_001", "to_node_id": "tx_001", "params": {"enabled": True}},
            {
                "id": "edge_tx_bus",
                "from_node_id": "tx_001",
                "to_node_id": "bus_001",
                "params": {"length_km": 1.0, "linecode": "LC_MAIN", "phases": 3, "rated_current_a": 100, "emerg_current_a": 120},
            },
            {
                "id": "edge_bus_load",
                "from_node_id": "bus_001",
                "to_node_id": "load_001",
                "params": {"length_km": 0.1, "linecode": "LC_BRANCH", "phases": 3, "rated_current_a": 100, "emerg_current_a": 120},
            },
        ],
        "economic_parameters": {},
    }

    validation = service._validate_topology(topology)
    assert any("同一 OpenDSS 母线" in item for item in validation["errors"])

    node_map = {str(node["id"]): node for node in topology["nodes"]}
    review = builder._build_model_review("proj01", topology["nodes"], topology["edges"], node_map, tmp_path)
    assert any(item["code"] == "OPENDSS_LINE_SAME_BUS" for item in review["issues"])
    assert "New Line.edge_bus_load" not in builder._build_lines(topology["edges"], node_map)


def test_dss_name_sanitizers_are_ascii_consistent():
    build_service = BuildExportService(data_root="unused")
    builder = DssBuilderService()
    solver = SolverExecutionService(data_root="unused")

    assert build_service._safe_name("母线-A") == "A"
    assert build_service._dss_safe_name("母线-A") == "A"
    assert builder._safe_name("母线-A") == "A"
    assert solver._safe_name("母线-A") == "A"


def test_storage_apparent_power_uses_power_not_energy_capacity():
    builder = DssBuilderService()

    storage_node = {
        "id": "storage_001",
        "type": "storage",
        "params": {
            "rated_kw": 100,
            "rated_kwh": 215,
        },
    }

    assert builder._resource_apparent_power_kva(storage_node) == 100


def test_load_internal_ids_are_validated_after_path_sanitizing():
    service = BuildExportService(data_root="unused")
    topology = {
        "nodes": [
            {"id": "grid_001", "type": "grid", "name": "grid", "params": {"base_kv": 110}},
            {"id": "tx_001", "type": "transformer", "name": "tx", "params": {"rated_kva": 31500}},
            {
                "id": "负荷-A",
                "type": "load",
                "name": "load A",
                "params": {"node_id": 1, "target_kv_ln": 0.4, "dss_bus_name": "n1", "dss_load_name": "LD01"},
            },
            {
                "id": "负荷 A",
                "type": "load",
                "name": "load B",
                "params": {"node_id": 2, "target_kv_ln": 0.4, "dss_bus_name": "n2", "dss_load_name": "LD02"},
            },
        ],
        "edges": [
            {"id": "e1", "from_node_id": "grid_001", "to_node_id": "tx_001", "params": {"length_km": 1}},
            {"id": "e2", "from_node_id": "tx_001", "to_node_id": "负荷-A", "params": {"length_km": 1}},
            {"id": "e3", "from_node_id": "tx_001", "to_node_id": "负荷 A", "params": {"length_km": 1}},
        ],
        "economic_parameters": {},
    }

    validation = service._validate_topology(topology)

    assert any("internal_model_id 重复" in item for item in validation["errors"])
