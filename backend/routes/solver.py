from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.solver_execution_service import SolverExecutionService
from services.project_model_service import ProjectModelService

router = APIRouter(prefix="/api/solver", tags=["project-solver"])
project_service = ProjectModelService()
solver_service = SolverExecutionService(project_service=project_service)


class SolverConfigureRequest(BaseModel):
    project_id: str | None = None
    solver_binding: dict[str, Any] = Field(default_factory=dict)


class SolverRunRequest(BaseModel):
    task_name: str | None = None
    disable_plots: bool | None = None
    output_subdir_name: str | None = None
    population_size: int | None = None
    generations: int | None = None
    target_id: str | None = None
    enable_opendss_oracle: bool | None = None
    initial_soc: float | None = None
    terminal_soc_mode: str | None = None
    fixed_terminal_soc_target: float | None = None
    daily_terminal_soc_tolerance: float | None = None


@router.post("/project/{project_id}/configure")
def configure_solver(project_id: str, request: SolverConfigureRequest) -> dict[str, Any]:
    try:
        binding = solver_service.configure_solver(project_id, request.solver_binding)
        return {
            "success": True,
            "project_id": project_id,
            "solver_binding": binding,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/config")
def get_solver_config(project_id: str) -> dict[str, Any]:
    try:
        binding = solver_service.get_solver_config(project_id)
        return {
            "success": True,
            "project_id": project_id,
            "solver_binding": binding,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/project/{project_id}/run")
def run_solver(project_id: str, request: SolverRunRequest | None = None) -> dict[str, Any]:
    try:
        task = solver_service.run_solver(project_id, request.model_dump() if request else {})
        return {
            "success": True,
            "task": task,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/task/{task_id}")
def get_task(task_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    task = solver_service.get_task(task_id, project_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"未找到任务：{task_id}")
    return {
        "success": True,
        "task": task,
    }


@router.get("/task/{task_id}/logs")
def get_task_logs(task_id: str, project_id: str | None = Query(default=None)) -> dict[str, Any]:
    task = solver_service.get_task_logs(task_id, project_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"未找到任务：{task_id}")
    return {
        "success": True,
        "task": task,
    }


@router.post("/project/{project_id}/task/{task_id}/cancel")
def cancel_task(project_id: str, task_id: str) -> dict[str, Any]:
    try:
        task = solver_service.cancel_task(task_id=task_id, project_id=project_id)
        return {
            "success": True,
            "task": task,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/latest")
def get_latest_task(project_id: str) -> dict[str, Any]:
    return {
        "success": True,
        "project_id": project_id,
        "task": solver_service.get_latest_task(project_id),
    }


@router.get("/project/{project_id}/tasks")
def list_solver_tasks(project_id: str) -> dict[str, Any]:
    try:
        return {"success": True, **solver_service.list_tasks(project_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/summary")
def get_project_summary(project_id: str, task_id: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return solver_service.get_project_summary(project_id, task_id=task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/results")
def get_project_results(project_id: str, task_id: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return solver_service.get_project_results(project_id, task_id=task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/charts")
def get_project_result_charts(project_id: str, task_id: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return solver_service.get_result_charts(project_id, task_id=task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/result-files")
def list_result_files(project_id: str, task_id: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        data = solver_service.list_result_files(project_id, task_id=task_id)
        return {
            "success": True,
            **data,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/result-file")
def get_result_file_preview(
    project_id: str,
    relative_path: str = Query(...),
    group: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return solver_service.get_result_file_preview(project_id, relative_path=relative_path, group=group, task_id=task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/result-file/download")
def download_result_file(
    project_id: str,
    relative_path: str = Query(...),
    group: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
) -> FileResponse:
    try:
        path, _ = solver_service.resolve_result_file_path(project_id, relative_path=relative_path, group=group, task_id=task_id)
        return FileResponse(path=str(path), filename=path.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
