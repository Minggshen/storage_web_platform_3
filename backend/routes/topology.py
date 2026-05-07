
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from models.project_model import (
    DeleteEdgeRequest,
    DeleteEdgeResponse,
    DeleteNodeRequest,
    DeleteNodeResponse,
    LoadProjectResponse,
    ReplaceTopologyResponse,
    TopologyCatalogResponse,
    UpsertEdgeRequest,
    UpsertEdgeResponse,
    UpsertNodeRequest,
    UpsertNodeResponse,
    ValidateProjectResponse,
    NetworkModel,
)
from services.network_topology_service import NetworkTopologyService
from services.project_model_service import ProjectModelService
from services.project_validation_service import ProjectValidationService


router = APIRouter(prefix="/api/topology", tags=["topology"])

project_service = ProjectModelService()
validation_service = ProjectValidationService()
topology_service = NetworkTopologyService()


@router.get("/catalog", response_model=TopologyCatalogResponse)
def get_topology_catalog() -> TopologyCatalogResponse:
    return TopologyCatalogResponse(
        success=True,
        node_catalog=topology_service.get_node_catalog(),
        edge_catalog=topology_service.get_edge_catalog(),
    )


@router.get("/project/{project_id}", response_model=LoadProjectResponse)
def get_project_topology(project_id: str) -> LoadProjectResponse:
    try:
        project = project_service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LoadProjectResponse(success=True, project=project)


def _parse_network_payload(project_id: str, payload: dict[str, Any]) -> NetworkModel:
    body_project_id = payload.get("project_id")
    if body_project_id is not None and str(body_project_id) != project_id:
        raise HTTPException(status_code=400, detail="路径 project_id 与请求体 project_id 不一致。")

    raw_network = payload.get("network") if isinstance(payload.get("network"), dict) else payload
    try:
        return NetworkModel(**raw_network)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"拓扑数据格式错误：{exc}") from exc


@router.put("/project/{project_id}", response_model=ReplaceTopologyResponse)
def replace_project_topology(project_id: str, request: dict[str, Any] = Body(...)) -> ReplaceTopologyResponse:
    network = _parse_network_payload(project_id, request)
    try:
        project, project_file = project_service.replace_topology(project_id, network)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReplaceTopologyResponse(success=True, project=project, project_file_path=str(project_file.resolve()))


@router.post("/node/upsert", response_model=UpsertNodeResponse)
def upsert_node(request: UpsertNodeRequest) -> UpsertNodeResponse:
    try:
        project, project_file = project_service.upsert_node(request.project_id, request.node)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return UpsertNodeResponse(success=True, project=project, project_file_path=str(project_file.resolve()))


@router.post("/node/delete", response_model=DeleteNodeResponse)
def delete_node(request: DeleteNodeRequest) -> DeleteNodeResponse:
    try:
        project, project_file, deleted_edge_ids = project_service.delete_node(request.project_id, request.node_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeleteNodeResponse(success=True, project=project, deleted_node_id=request.node_id, deleted_edge_ids=deleted_edge_ids, project_file_path=str(project_file.resolve()))


@router.post("/edge/upsert", response_model=UpsertEdgeResponse)
def upsert_edge(request: UpsertEdgeRequest) -> UpsertEdgeResponse:
    try:
        project, project_file = project_service.upsert_edge(request.project_id, request.edge)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return UpsertEdgeResponse(success=True, project=project, project_file_path=str(project_file.resolve()))


@router.post("/edge/delete", response_model=DeleteEdgeResponse)
def delete_edge(request: DeleteEdgeRequest) -> DeleteEdgeResponse:
    try:
        project, project_file = project_service.delete_edge(request.project_id, request.edge_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeleteEdgeResponse(success=True, project=project, deleted_edge_id=request.edge_id, project_file_path=str(project_file.resolve()))


@router.get("/project/{project_id}/validate", response_model=ValidateProjectResponse)
def validate_topology(project_id: str) -> ValidateProjectResponse:
    try:
        project = project_service.load_project(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = validation_service.validate(project)
    return ValidateProjectResponse(success=True, report=report)
