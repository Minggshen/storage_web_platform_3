
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from models.project_model import (
    DeleteEdgeRequest,
    DeleteEdgeResponse,
    DeleteNodeRequest,
    DeleteNodeResponse,
    LoadProjectResponse,
    ReplaceTopologyResponse,
    SaveTemplateRequest,
    TopologyCatalogResponse,
    TopologyTemplateDetailResponse,
    TopologyTemplateListResponse,
    TopologyTemplateMeta,
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

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "data" / "topology_templates"


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


# ── Topology template CRUD ──

def _ensure_templates_dir() -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR


@router.get("/templates", response_model=TopologyTemplateListResponse)
def list_templates() -> TopologyTemplateListResponse:
    _ensure_templates_dir()
    templates: list[TopologyTemplateMeta] = []
    for path in sorted(TEMPLATES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            nodes = data.get("topology", {}).get("nodes", [])
            edges = data.get("topology", {}).get("edges", [])
            templates.append(TopologyTemplateMeta(
                template_id=data.get("template_id", path.stem),
                name=data.get("name", path.stem),
                description=data.get("description", ""),
                created_at=data.get("created_at", ""),
                node_count=len(nodes) if isinstance(nodes, list) else 0,
                edge_count=len(edges) if isinstance(edges, list) else 0,
            ))
        except Exception:
            continue
    return TopologyTemplateListResponse(success=True, templates=templates)


@router.get("/templates/{template_id}", response_model=TopologyTemplateDetailResponse)
def get_template(template_id: str) -> TopologyTemplateDetailResponse:
    _ensure_templates_dir()
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在。")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读取模板失败：{exc}") from exc
    return TopologyTemplateDetailResponse(success=True, template=data)


@router.post("/templates", response_model=TopologyTemplateDetailResponse)
def save_template(request: SaveTemplateRequest) -> TopologyTemplateDetailResponse:
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="模板名称不能为空。")
    _ensure_templates_dir()
    template_id = uuid.uuid4().hex[:12]
    data: dict[str, Any] = {
        "template_id": template_id,
        "name": request.name.strip(),
        "description": (request.description or "").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "topology": request.topology,
    }
    path = TEMPLATES_DIR / f"{template_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return TopologyTemplateDetailResponse(success=True, template=data)


@router.delete("/templates/{template_id}")
def delete_template(template_id: str) -> dict[str, Any]:
    _ensure_templates_dir()
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在。")
    path.unlink()
    return {"success": True, "template_id": template_id}
