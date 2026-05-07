
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.project_model import SearchSpaceInferenceResponse
from services.build_export_service import BuildExportService
from services.build_inference_service import BuildInferenceService
from services.project_model_service import ProjectModelService


router = APIRouter(prefix="/api/build", tags=["project-build"])

project_service = ProjectModelService()
build_service = BuildExportService(project_service=project_service)
inference_service = BuildInferenceService(project_service=project_service)


class BuildGenerationRequest(BaseModel):
    clean_build_dir: bool = True
    package_zip: bool = True
    export_registry_xlsx: bool = True


@router.get("/project/{project_id}/preview")
def preview_build(project_id: str) -> dict[str, Any]:
    try:
        return build_service.preview_build(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/{project_id}/inference-table", response_model=SearchSpaceInferenceResponse)
def get_inference_table(project_id: str) -> SearchSpaceInferenceResponse:
    try:
        rows = inference_service.get_inference_rows(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SearchSpaceInferenceResponse(success=True, project_id=project_id, rows=rows)


@router.post("/project/{project_id}/generate")
def generate_project_workspace(project_id: str, request: BuildGenerationRequest) -> dict[str, Any]:
    try:
        return build_service.generate_build(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_id}/manifest")
def get_build_manifest(project_id: str) -> dict[str, Any]:
    try:
        return build_service.read_build_manifest(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/project/{project_id}/grid-health")
def check_grid_health(project_id: str) -> dict[str, Any]:
    try:
        from services.dss_builder_service import DssBuilderService
        
        project = project_service.load_project(project_id)
        nodes = [
            {
                "id": node.id,
                "type": node.type.value if hasattr(node.type, "value") else str(node.type),
                "label": node.name,
                "params": node.params or {},
            }
            for node in project.network.nodes
        ]
        edges = [
            {
                "id": edge.id,
                "from_node_id": edge.from_node_id,
                "to_node_id": edge.to_node_id,
                "params": edge.params or {},
            }
            for edge in project.network.edges
        ]
        node_map = {str(node["id"]): node for node in nodes}
        
        builder = DssBuilderService()
        health_result = builder.validate_grid_health(nodes, edges, node_map)
        
        return {
            "success": True,
            "project_id": project_id,
            "grid_health": health_result,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
