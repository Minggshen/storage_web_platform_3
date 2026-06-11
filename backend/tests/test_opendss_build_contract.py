from __future__ import annotations

import json
import os
import subprocess
import sys

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


def test_dss_name_sanitizers_are_ascii_consistent():
    build_service = BuildExportService(data_root="unused")
    builder = DssBuilderService()
    solver = SolverExecutionService(data_root="unused")

    assert build_service._safe_name("母线-A") == "A"
    assert build_service._dss_safe_name("母线-A") == "A"
    assert builder._safe_name("母线-A") == "A"
    assert solver._safe_name("母线-A") == "A"


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
