from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.solver_execution_service import SolverExecutionService  # noqa: E402


def _write_task(
    data_root: Path,
    project_id: str,
    task_id: str,
    *,
    status: str = "failed",
    pid: int | None = None,
) -> Path:
    task_dir = data_root / project_id / "solver_runs" / f"task_{task_id}"
    state_dir = task_dir / "state"
    output_dir = task_dir / "solver_workspace" / "outputs" / "integrated_optimization"
    state_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (task_dir / "stdout.log").write_text("stdout", encoding="utf-8")
    (task_dir / "stderr.log").write_text("stderr", encoding="utf-8")
    payload = {
        "task_id": task_id,
        "project_id": project_id,
        "status": status,
        "pid": pid,
        "started_at": "2026-06-10T10:00:00+08:00",
        "completed_at": "2026-06-10T10:05:00+08:00" if status != "running" else None,
        "stdout_log": str(task_dir / "stdout.log"),
        "stderr_log": str(task_dir / "stderr.log"),
        "outputs_dir": str(output_dir),
        "solver_workspace": str(task_dir / "solver_workspace"),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    (task_dir / "task_meta.json").write_text(text, encoding="utf-8")
    (state_dir / "task.json").write_text(text, encoding="utf-8")
    return task_dir


def test_delete_task_removes_only_selected_task_directory(tmp_path: Path) -> None:
    project_id = "proj123"
    task_id = "deadbeef0001"
    service = SolverExecutionService(data_root=tmp_path)
    project_dir = tmp_path / project_id
    shared_build_file = project_dir / "build" / "solver_workspace" / "inputs" / "registry.xlsx"
    shared_asset_file = project_dir / "assets" / "tariff" / "price.xlsx"
    shared_build_file.parent.mkdir(parents=True)
    shared_asset_file.parent.mkdir(parents=True)
    shared_build_file.write_text("shared build", encoding="utf-8")
    shared_asset_file.write_text("shared asset", encoding="utf-8")
    target_task_dir = _write_task(tmp_path, project_id, task_id)
    sibling_task_dir = _write_task(tmp_path, project_id, "feedface0002")
    (target_task_dir / "solver_workspace" / "outputs" / "integrated_optimization" / "result.csv").write_text(
        "a,b\n1,2\n",
        encoding="utf-8",
    )

    result = service.delete_task(project_id, task_id)

    assert result["deleted_scope"] == f"solver_runs/task_{task_id}"
    assert result["status_before_delete"] == "failed"
    assert result["deleted_file_count"] >= 4
    assert not target_task_dir.exists()
    assert sibling_task_dir.exists()
    assert shared_build_file.exists()
    assert shared_asset_file.exists()


def test_delete_task_accepts_display_prefix_but_rejects_path_escape(tmp_path: Path) -> None:
    project_id = "proj123"
    task_id = "abc123def456"
    service = SolverExecutionService(data_root=tmp_path)
    target_task_dir = _write_task(tmp_path, project_id, task_id)

    result = service.delete_task(project_id, f"task_{task_id}")

    assert result["task_id"] == task_id
    assert not target_task_dir.exists()

    _write_task(tmp_path, project_id, task_id)
    with pytest.raises(ValueError):
        service.delete_task(project_id, "../build")
    with pytest.raises(ValueError):
        service.delete_task(project_id, "abc/def")


def test_delete_task_rejects_active_running_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_id = "proj123"
    task_id = "running0001"
    service = SolverExecutionService(data_root=tmp_path)
    task_dir = _write_task(tmp_path, project_id, task_id, status="running", pid=12345)
    monkeypatch.setattr(service, "_pid_matches_task_process", lambda pid, task: True)

    with pytest.raises(ValueError, match="任务仍在运行"):
        service.delete_task(project_id, task_id)

    assert task_dir.exists()


def test_delete_task_rejects_queued_task(tmp_path: Path) -> None:
    project_id = "proj123"
    task_id = "queued0001"
    service = SolverExecutionService(data_root=tmp_path)
    task_dir = _write_task(tmp_path, project_id, task_id, status="queued")

    with pytest.raises(ValueError, match="任务仍在运行"):
        service.delete_task(project_id, task_id)

    assert task_dir.exists()


def test_delete_task_allows_stale_interrupted_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_id = "proj123"
    task_id = "stale0001"
    service = SolverExecutionService(data_root=tmp_path)
    task_dir = _write_task(tmp_path, project_id, task_id, status="running", pid=12345)
    monkeypatch.setattr(service, "_pid_matches_task_process", lambda pid, task: False)

    result = service.delete_task(project_id, task_id)

    assert result["status_before_delete"] == "failed"
    assert not task_dir.exists()
