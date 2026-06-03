from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

# Allow `from services...` imports when pytest runs from repo root.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Keep this focused unit test independent from FastAPI/anyio imports.
_project_model_stub = types.ModuleType("services.project_model_service")
_project_model_stub.ProjectModelService = type("ProjectModelService", (), {})
sys.modules.setdefault("services.project_model_service", _project_model_stub)

from services.solver_execution_service import SolverExecutionService  # noqa: E402


def _write_trace_files(case_dir: Path, *, voltage_min: str = "0.95", loading_pct: str = "70") -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "best_bus_voltage_trace.csv").write_text(
        "\n".join(
            [
                "bus,baseline_voltage_pu_min,baseline_voltage_pu_max,voltage_pu_min,voltage_pu_max",
                f"bus_a,0.94,1.02,{voltage_min},1.01",
            ]
        ),
        encoding="utf-8",
    )
    (case_dir / "best_line_loading_trace.csv").write_text(
        "\n".join(
            [
                "line,current_a,loading_pct,normamps,terminal1_power_kw",
                f"line.feeder_1,100,{loading_pct},200,50",
            ]
        ),
        encoding="utf-8",
    )


def _build_summaries(service: SolverExecutionService, case_dir: Path):
    return service._load_or_build_network_topology_trace_summaries(case_dir, {"bus_a": 0.4})


def _write_task(service: SolverExecutionService, project_id: str, task: dict) -> None:
    task_dir = service._task_dir(project_id, str(task["task_id"]))
    task_dir.mkdir(parents=True, exist_ok=True)
    service._write_task_files(task_dir, task)


def test_output_subdir_name_validation_accepts_safe_names() -> None:
    assert SolverExecutionService._validate_output_subdir_name(None) == "integrated_optimization"
    assert SolverExecutionService._validate_output_subdir_name("custom-run_1.2") == "custom-run_1.2"


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "..\\escape",
        "C:\\escape",
        "/tmp/escape",
        ".",
        "..",
        "bad name",
    ],
)
def test_output_subdir_name_validation_rejects_path_segments(name: str) -> None:
    with pytest.raises(ValueError):
        SolverExecutionService._validate_output_subdir_name(name)


def test_structured_progress_marker_refines_candidate_span_with_proxy_progress(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    stdout = "\n".join(
        [
            '2026-06-01 10:00:00 [INFO] storage_engine_project.main: SOLVER_PROGRESS {"percent":20,"label":"GA 候选评估","detail":"第 1/1 个场景，候选 3/12。","phase":"ga_candidate","span_start_percent":20,"span_end_percent":30}',
            "2026-06-01 10:00:01 [INFO] storage_engine_project.simulation.annual_operation_kernel: 年度运行 代表日 5/10 | rep_day=57 | 覆盖天数=14 | 当前日初SOC=0.2500",
        ]
    )

    progress = service._parse_stdout_progress(stdout, requested_generations=5)

    assert progress["source"] == "solver_progress_marker"
    assert progress["percent"] == 25
    assert progress["label"] == "GA 候选评估"
    assert "代表日运行 5/10" in progress["detail"]


def test_structured_progress_marker_refines_recheck_span_with_annual_days(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    stdout = "\n".join(
        [
            '2026-06-01 10:00:00 [INFO] storage_engine_project.main: SOLVER_PROGRESS {"percent":44,"label":"OpenDSS 全年重校核","detail":"正在重校核 Top-1/3 候选。","phase":"topk_recheck_candidate","span_start_percent":44,"span_end_percent":60}',
            "2026-06-01 10:00:01 [INFO] storage_engine_project.simulation.annual_operation_kernel: 年度运行 进度 183/365 | 当前日初SOC=0.4821 | 策略=S1",
        ]
    )

    progress = service._parse_stdout_progress(stdout, requested_generations=5)

    assert progress["source"] == "solver_progress_marker"
    assert progress["percent"] == 52
    assert "183/365" in progress["detail"]


def test_legacy_progress_no_longer_reports_fake_final_population_eval(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    stdout = "\n".join(
        [
            "2026-06-01 10:00:00 [INFO] storage_engine_project.main: 共加载 1 个待优化场景。",
            "2026-06-01 10:00:01 [INFO] storage_engine_project.main: 开始场景优化 [1/1]：load_01 | 总代数=5 | 每代种群=12",
            "2026-06-01 10:05:00 [INFO] storage_engine_project.optimization.lemming_optimizer: 优化迭代 5 | 种群=12 | 可行解=4 | Archive=6",
        ]
    )

    progress = service._parse_stdout_progress(stdout, requested_generations=5)

    assert progress["label"] == "GA 搜索已完成"
    assert "准备全年重校核" in progress["detail"]


def test_network_topology_trace_summary_cache_hit_skips_trace_rescan(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    case_dir = tmp_path / "case"
    _write_trace_files(case_dir)

    bus_summary, line_summary = _build_summaries(service, case_dir)
    assert bus_summary["bus_a"]["voltagePuMin"] == pytest.approx(0.95)
    assert line_summary["feeder_1"]["loadingPct"] == pytest.approx(70.0)
    assert (case_dir / service.NETWORK_TOPOLOGY_SUMMARY_CACHE_FILE).exists()
    assert service._last_network_topology_cache_diagnostics["status"] == "rebuilt"

    original_bus_summary = service._summarize_bus_voltage_trace
    original_line_summary = service._summarize_line_loading_trace
    service._summarize_bus_voltage_trace = lambda *_, **__: (_ for _ in ()).throw(AssertionError("bus trace was rescanned"))  # type: ignore[method-assign]
    service._summarize_line_loading_trace = lambda *_, **__: (_ for _ in ()).throw(AssertionError("line trace was rescanned"))  # type: ignore[method-assign]
    try:
        cached_bus_summary, cached_line_summary = _build_summaries(service, case_dir)
    finally:
        service._summarize_bus_voltage_trace = original_bus_summary  # type: ignore[method-assign]
        service._summarize_line_loading_trace = original_line_summary  # type: ignore[method-assign]

    assert cached_bus_summary == bus_summary
    assert cached_line_summary == line_summary
    assert service._last_network_topology_cache_diagnostics["status"] == "hit"


def test_network_topology_trace_summary_cache_invalidates_when_source_changes(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    case_dir = tmp_path / "case"
    _write_trace_files(case_dir, voltage_min="0.95")
    _build_summaries(service, case_dir)

    _write_trace_files(case_dir, voltage_min="0.9000")
    bus_summary, _ = _build_summaries(service, case_dir)

    assert bus_summary["bus_a"]["voltagePuMin"] == pytest.approx(0.9)
    assert service._last_network_topology_cache_diagnostics["status"] == "rebuilt"
    assert service._last_network_topology_cache_diagnostics["reason"] == "invalid_cache"


def test_network_topology_trace_summary_cache_rebuilds_after_corruption(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    case_dir = tmp_path / "case"
    _write_trace_files(case_dir)
    _build_summaries(service, case_dir)

    cache_path = case_dir / service.NETWORK_TOPOLOGY_SUMMARY_CACHE_FILE
    cache_path.write_text("{not-json", encoding="utf-8")

    bus_summary, line_summary = _build_summaries(service, case_dir)
    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))

    assert bus_summary["bus_a"]["voltagePuMax"] == pytest.approx(1.01)
    assert line_summary["feeder_1"]["currentA"] == pytest.approx(100.0)
    assert isinstance(cache_payload.get("metadata"), dict)
    assert service._last_network_topology_cache_diagnostics["status"] == "rebuilt"


def test_network_topology_trace_summary_cache_handles_missing_traces(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    case_dir = tmp_path / "case"
    case_dir.mkdir()

    bus_summary, line_summary = _build_summaries(service, case_dir)
    cache_payload = json.loads((case_dir / service.NETWORK_TOPOLOGY_SUMMARY_CACHE_FILE).read_text(encoding="utf-8"))

    assert bus_summary == {}
    assert line_summary == {}
    assert cache_payload["metadata"]["bus_voltage_trace"]["exists"] is False
    assert cache_payload["metadata"]["line_loading_trace"]["exists"] is False
    assert service._last_network_topology_cache_diagnostics["status"] == "missing"


def test_run_health_report_normalization_adds_status_and_structured_issue(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    report = {
        "status": "failed",
        "summary": {"issue_count": 1, "error_count": 1, "warning_count": 0},
        "issues": [
            {
                "severity": "error",
                "code": "opendss_not_converged",
                "message": "OpenDSS 未收敛。",
                "details": {},
            }
        ],
    }

    normalized = service._normalize_run_health_report(report)

    assert normalized["status"] == "critical"
    assert normalized["legacy_status"] == "failed"
    assert normalized["summary"]["critical_count"] == 1
    assert normalized["issues"][0]["level"] == "critical"
    assert normalized["issues"][0]["related_section"] == "network_impact"


def test_task_brief_reads_health_status_for_completed_task(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    case_dir = tmp_path / "proj" / "solver_runs" / "task_t1" / "solver_workspace" / "outputs" / "integrated_optimization" / "load_01"
    case_dir.mkdir(parents=True)
    (case_dir / "run_health_report.json").write_text(
        json.dumps({"status": "warning", "summary": {"issue_count": 2, "warning_count": 2}, "issues": []}),
        encoding="utf-8",
    )

    brief = service._task_brief({"task_id": "t1", "status": "completed"}, project_id="proj")

    assert brief["health_status"] == "warning"
    assert brief["health_issue_count"] == 2
    assert brief["health_warning_count"] == 2


def test_network_impact_normalization_adds_target_and_transformer_summary(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    report = {
        "target_connection": {
            "delta": {
                "safety_violation_hours": -3,
                "max_voltage_violation_pu": 0,
                "max_line_loading_pct": -4,
            }
        },
        "baseline": {"transformer_overload_hours": 1},
        "with_storage": {"transformer_overload_hours": 5},
        "delta": {"safety_violation_hours": -3, "loss_reduction_kwh": 10, "max_voltage_violation_pu": 0, "max_line_loading_pct": -4},
        "risk_details": {
            "voltage_classification_counts": {"storage_induced": 1},
            "line_classification_counts": {"worsened_by_storage": 2},
            "transformer": {
                "baseline_overload_hours": 1,
                "with_storage_overload_hours": 5,
                "classification": "worsened_by_storage",
            },
        },
    }

    normalized = service._normalize_network_impact_report(report)

    assert normalized["target_area_conclusion"]["status"] == "worsened"
    assert normalized["risk_classification_summary"]["total_risks"] == 4
    assert normalized["transformer_top_risks"][0]["overload_hour_delta"] == pytest.approx(4)
    assert "line_loading" in normalized["attribution_summary"]


def test_get_task_auto_settles_stale_running_task_when_pid_is_missing(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    project_id = "proj"
    task = {
        "task_id": "t1",
        "project_id": project_id,
        "status": "running",
        "pid": 999999,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "outputs_dir": str(tmp_path / "missing_outputs"),
        "metadata": {},
        "progress_hint": {"percent": 39},
    }
    _write_task(service, project_id, task)
    service._pid_matches_task_process = lambda _pid, _task: False  # type: ignore[method-assign]

    settled = service.get_task("t1", project_id)

    assert settled is not None
    assert settled["status"] == "failed"
    assert settled["completed_at"]
    assert settled["metadata"]["auto_settle_reason"] == "process_not_found"
    assert settled["progress_hint"]["label"] == "运行中断"


def test_get_task_auto_settles_stale_running_task_as_completed_when_outputs_exist(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    project_id = "proj"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    (output_dir / "overall_best_schemes.json").write_text(
        json.dumps([{"internal_model_id": "LD1"}], ensure_ascii=False),
        encoding="utf-8",
    )
    task = {
        "task_id": "t2",
        "project_id": project_id,
        "status": "running",
        "pid": 999999,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "outputs_dir": str(output_dir),
        "metadata": {},
    }
    _write_task(service, project_id, task)
    service._pid_matches_task_process = lambda _pid, _task: False  # type: ignore[method-assign]

    settled = service.get_task("t2", project_id)

    assert settled is not None
    assert settled["status"] == "completed"
    assert settled["progress_hint"]["percent"] == 100
    assert settled["metadata"]["summary_rows"] == [{"internal_model_id": "LD1"}]


def test_cancel_task_marks_missing_process_as_cancelled(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    project_id = "proj"
    task = {
        "task_id": "t3",
        "project_id": project_id,
        "status": "running",
        "pid": 999999,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "metadata": {},
        "progress_hint": {"percent": 12},
    }
    _write_task(service, project_id, task)
    service._pid_matches_task_process = lambda _pid, _task: True  # type: ignore[method-assign]
    service._terminate_process_tree = lambda _pid: {  # type: ignore[method-assign]
        "return_code": 128,
        "stdout": "",
        "stderr": 'ERROR: The process "999999" not found.',
        "not_found": True,
    }

    cancelled = service.cancel_task("t3", project_id)

    assert cancelled["status"] == "cancelled"
    assert cancelled["completed_at"]
    assert cancelled["metadata"]["cancel_result"]["not_found"] is True
    assert "已不存在" in cancelled["message"]


def test_get_task_auto_settles_legacy_cancelling_taskkill_not_found(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    project_id = "proj"
    task = {
        "task_id": "t4",
        "project_id": project_id,
        "status": "cancelling",
        "pid": 999999,
        "started_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "metadata": {
            "cancel_result": {
                "return_code": 128,
                "stdout": "",
                "stderr": 'ERROR: The process "999999" not found.',
            }
        },
        "progress_hint": {"percent": 39},
    }
    _write_task(service, project_id, task)
    service._pid_matches_task_process = lambda _pid, _task: True  # type: ignore[method-assign]

    settled = service.get_task("t4", project_id)

    assert settled is not None
    assert settled["status"] == "cancelled"
    assert settled["metadata"]["auto_settle_reason"] == "cancel_process_not_found"
    assert settled["progress_hint"]["label"] == "运行已终止"
