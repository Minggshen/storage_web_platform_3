
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.project_model import (
    CloneProjectRequest,
    CloneProjectResponse,
    CreateProjectRequest,
    CreateProjectResponse,
    DeleteProjectResponse,
    ListProjectsResponse,
    LoadProjectResponse,
    ProjectDashboardResponse,
    SaveProjectRequest,
    SaveProjectResponse,
    ValidateProjectRequest,
    ValidateProjectResponse,
)
from services.file_store import UPLOAD_DIR, save_upload
from services.project_dashboard_service import ProjectDashboardService
from services.project_model_service import ProjectModelService
from services.project_validation_service import ProjectValidationService
from services.task_service import new_id
from services.validation_service import validate_all_inputs


router = APIRouter(tags=["project-model"])

project_service = ProjectModelService()
validation_service = ProjectValidationService()
dashboard_service = ProjectDashboardService(project_service=project_service)


@router.get("/api/project/health")
def project_health() -> dict:
    return {"success": True, "message": "project router ok"}


@router.get("/api/projects", response_model=ListProjectsResponse)
def get_projects() -> ListProjectsResponse:
    return ListProjectsResponse(success=True, projects=project_service.list_projects())


@router.post("/api/projects", response_model=CreateProjectResponse)
def create_project(request: CreateProjectRequest) -> CreateProjectResponse:
    project_name = (request.project_name or request.name or "").strip()
    if not project_name:
        raise HTTPException(status_code=400, detail="项目名称不能为空。")
    project, project_file = project_service.create_empty_project(
        project_name=project_name,
        description=request.description,
    )
    return CreateProjectResponse(success=True, project=project, project_file_path=str(project_file.resolve()))


@router.delete("/api/project/{project_id}", response_model=DeleteProjectResponse)
def delete_project(project_id: str) -> DeleteProjectResponse:
    try:
        deleted_path = project_service.delete_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeleteProjectResponse(success=True, project_id=project_id, deleted_path=str(deleted_path.resolve()))


@router.post("/api/project/{project_id}/clone", response_model=CloneProjectResponse)
def clone_project(project_id: str, request: CloneProjectRequest) -> CloneProjectResponse:
    try:
        project, project_file = project_service.clone_project(project_id, request.new_project_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CloneProjectResponse(
        success=True,
        source_project_id=project_id,
        project=project,
        project_file_path=str(project_file.resolve()),
    )


@router.get("/api/project/{project_id}/dashboard", response_model=ProjectDashboardResponse)
def get_project_dashboard(project_id: str) -> ProjectDashboardResponse:
    try:
        dashboard = dashboard_service.get_dashboard(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectDashboardResponse(success=True, dashboard=dashboard)


# Backward-compatible endpoints
@router.post("/api/project/create-empty", response_model=CreateProjectResponse)
def create_empty_project_compat(request: CreateProjectRequest) -> CreateProjectResponse:
    return create_project(request)


@router.post("/api/project/save", response_model=SaveProjectResponse)
def save_project(request: SaveProjectRequest) -> SaveProjectResponse:
    project_id, project_file = project_service.save_project(request.project)
    return SaveProjectResponse(success=True, project_id=project_id, project_file_path=str(project_file.resolve()))


@router.get("/api/project/list", response_model=ListProjectsResponse)
def list_projects_compat() -> ListProjectsResponse:
    return get_projects()


@router.get("/api/project/{project_id}", response_model=LoadProjectResponse)
def load_project(project_id: str) -> LoadProjectResponse:
    try:
        project = project_service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoadProjectResponse(success=True, project=project)


@router.post("/api/project/validate", response_model=ValidateProjectResponse)
def validate_project(request: ValidateProjectRequest) -> ValidateProjectResponse:
    report = validation_service.validate(request.project)
    return ValidateProjectResponse(success=True, report=report)


@router.post("/api/project/validate-files")
async def validate_project_files(
    scene_name: str = Form(...),
    strict_tariff: bool = Form(True),
    registry_file: UploadFile | None = File(default=None),
    tariff_file: UploadFile | None = File(default=None),
    runtime_year_map_file: UploadFile | None = File(default=None),
    runtime_model_library_file: UploadFile | None = File(default=None),
    storage_file: UploadFile | None = File(default=None),
    dss_file: UploadFile | None = File(default=None),
):
    validation_dir = UPLOAD_DIR / new_id("val")
    validation_dir.mkdir(parents=True, exist_ok=True)

    registry_path = await save_upload(registry_file, validation_dir, "registry")
    tariff_path = await save_upload(tariff_file, validation_dir, "tariff")
    runtime_year_map_path = await save_upload(runtime_year_map_file, validation_dir, "runtime")
    runtime_model_library_path = await save_upload(runtime_model_library_file, validation_dir, "runtime")
    storage_path = await save_upload(storage_file, validation_dir, "storage")
    dss_path = await save_upload(dss_file, validation_dir, "dss")

    summary = validate_all_inputs(
        scene_name=scene_name,
        strict_tariff=bool(strict_tariff),
        registry_path=registry_path,
        tariff_path=tariff_path,
        runtime_year_map_path=runtime_year_map_path,
        runtime_model_library_path=runtime_model_library_path,
        storage_path=storage_path,
        dss_path=dss_path,
        saved_dir=validation_dir,
    )
    return summary.model_dump()


@router.get("/api/project/{project_id}/validate", response_model=ValidateProjectResponse)
def validate_saved_project(project_id: str) -> ValidateProjectResponse:
    try:
        project = project_service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = validation_service.validate(project)
    return ValidateProjectResponse(success=True, report=report)
