from __future__ import annotations

import csv
import io
from pathlib import Path
from urllib.parse import quote

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse, Response

from models.load_data_models import (
    RawLoadDataUploadResponse,
    ProcessRuntimeRequest,
    PreviewFileInfo,
    PreviewNodeResponse,
)
from models.project_model import (
    DeleteDeviceRecordRequest,
    DeleteDeviceRecordResponse,
    ProjectAssetsResponse,
    RuntimeBindingRequest,
    RuntimeBindingResponse,
    RuntimeUploadResponse,
    TariffBindingRequest,
    TariffBindingResponse,
    TariffUploadResponse,
    DeviceLibraryUploadResponse,
    UpsertDeviceRecordRequest,
    UpsertDeviceRecordResponse,
)
from services.asset_binding_service import AssetBindingService
from services.asset_binding_service import RUNTIME_FILE_SUFFIXES
from services.load_data_processing_service import LoadDataProcessingService
from services.project_model_service import ProjectModelService


router = APIRouter(prefix="/api/assets", tags=["assets-binding"])

project_service = ProjectModelService()
asset_service = AssetBindingService(project_service=project_service)
processing_service = LoadDataProcessingService(project_service=project_service)
PREVIEW_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
}
PREVIEW_IMAGE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'",
}


def _project_asset_file_path(project_id: str, stored_path: object) -> Path:
    if not stored_path:
        raise ValueError("资产缺少 stored_path，无法绑定。")
    try:
        resolved = Path(str(stored_path)).resolve()
        assets_dir = (project_service._project_dir(project_id) / "assets").resolve()
        resolved.relative_to(assets_dir)
    except (OSError, ValueError) as exc:
        raise ValueError("资产文件路径不在当前项目 assets 目录内，拒绝绑定。") from exc
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"资产文件不存在：{resolved}")
    return resolved


@router.get("/project/{project_id}", response_model=ProjectAssetsResponse)
def list_project_assets(project_id: str) -> ProjectAssetsResponse:
    try:
        assets = project_service.list_assets(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectAssetsResponse(success=True, project_id=project_id, assets=assets)


@router.post("/runtime/upload", response_model=RuntimeUploadResponse)
def upload_runtime_files(
    project_id: str = Form(...),
    node_id: str = Form(...),
    year_map_file: UploadFile = File(...),
    model_library_file: UploadFile = File(...),
) -> RuntimeUploadResponse:
    try:
        year_map_asset, year_map_report, model_asset, model_report, project, project_file = asset_service.upload_runtime_files(
            project_id=project_id,
            node_id=node_id,
            year_map_file=year_map_file,
            model_library_file=model_library_file,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RuntimeUploadResponse(
        success=True,
        project=project,
        node_id=node_id,
        year_map_asset=year_map_asset,
        model_library_asset=model_asset,
        year_map_report=year_map_report,
        model_library_report=model_report,
        project_file_path=str(project_file.resolve()),
    )


@router.post("/runtime/bind", response_model=RuntimeBindingResponse)
def bind_existing_runtime_files(request: RuntimeBindingRequest) -> RuntimeBindingResponse:
    try:
        project = project_service.load_project(request.project_id)
        year_asset = project_service.get_asset(project, request.year_map_file_id)
        model_asset = project_service.get_asset(project, request.model_library_file_id)
        year_path = _project_asset_file_path(request.project_id, year_asset.metadata.get("stored_path"))
        model_path = _project_asset_file_path(request.project_id, model_asset.metadata.get("stored_path"))
        year_report = asset_service.validate_runtime_year_map(year_path)
        model_report = asset_service.validate_runtime_model_library(model_path)
        if not year_report.ok or not model_report.ok:
            message = asset_service._validation_failure_message(
                [year_report, model_report],
                "负荷 runtime 文件校验未通过，未绑定为当前文件",
            )
            raise ValueError(message)
        project, project_file = project_service.bind_runtime_assets(
            project_id=request.project_id,
            node_id=request.node_id,
            year_map_asset=year_asset,
            model_library_asset=model_asset,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RuntimeBindingResponse(
        success=True,
        project=project,
        node_id=request.node_id,
        year_map_asset=year_asset,
        model_library_asset=model_asset,
        year_map_report=year_report,
        model_library_report=model_report,
        project_file_path=str(project_file.resolve()),
    )


@router.post("/tariff/upload", response_model=TariffUploadResponse)
def upload_tariff_file(
    project_id: str = Form(...),
    tariff_file: UploadFile = File(...),
) -> TariffUploadResponse:
    try:
        asset, report, project, project_file = asset_service.upload_tariff_file(
            project_id=project_id,
            tariff_file=tariff_file,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TariffUploadResponse(
        success=True,
        project=project,
        asset=asset,
        report=report,
        project_file_path=str(project_file.resolve()),
    )


@router.post("/project/{project_id}/tariff/upload")
def upload_tariff_file_compat(
    project_id: str,
    file: UploadFile = File(...),
) -> TariffUploadResponse:
    return upload_tariff_file(project_id=project_id, tariff_file=file)


@router.post("/tariff/bind", response_model=TariffBindingResponse)
def bind_existing_tariff_file(request: TariffBindingRequest) -> TariffBindingResponse:
    try:
        project = project_service.load_project(request.project_id)
        asset = project_service.get_asset(project, request.file_id)
        stored_path = _project_asset_file_path(request.project_id, asset.metadata.get("stored_path"))
        report = asset_service.validate_tariff_file(stored_path)
        if not report.ok:
            raise ValueError(asset_service._validation_failure_message([report], "电价表校验未通过，未绑定为当前文件"))
        asset.metadata["validation"] = report.model_dump(mode="json")
        project.assets[asset.file_id] = asset
        project, project_file = project_service.bind_tariff_asset(
            project_id=request.project_id,
            asset=asset,
            tariff_year=request.tariff_year or report.parsed_preview.get("detected_year"),
        )
        project.assets[asset.file_id] = asset
        _, project_file = project_service.save_project(project)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TariffBindingResponse(
        success=True,
        project=project,
        asset=asset,
        report=report,
        project_file_path=str(project_file.resolve()),
    )


@router.post("/device-library/upload", response_model=DeviceLibraryUploadResponse)
def upload_device_library(
    project_id: str = Form(...),
    device_file: UploadFile = File(...),
) -> DeviceLibraryUploadResponse:
    try:
        asset, report, records, project, project_file = asset_service.upload_device_library_file(
            project_id=project_id,
            device_file=device_file,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeviceLibraryUploadResponse(
        success=True,
        project=project,
        asset=asset,
        report=report,
        imported_record_count=len(records),
        project_file_path=str(project_file.resolve()),
    )


@router.post("/project/{project_id}/device-library/upload")
def upload_device_library_compat(
    project_id: str,
    file: UploadFile = File(...),
) -> DeviceLibraryUploadResponse:
    return upload_device_library(project_id=project_id, device_file=file)


@router.post("/project/{project_id}/runtime/upload")
def upload_runtime_file_compat(
    project_id: str,
    node_id: str = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if kind not in {"year_map", "model_library"}:
        raise HTTPException(status_code=400, detail="kind 必须为 year_map 或 model_library。")

    try:
        project_service.ensure_load_node(project_id, node_id)
        asset_service._ensure_upload_suffix(file, RUNTIME_FILE_SUFFIXES, "负荷 runtime 文件")
        asset, path, project, project_file = project_service.save_asset_upload(
            project_id=project_id,
            upload_file=file,
            category="runtime",
            subfolder=node_id,
            metadata={"runtime_kind": kind, "node_id": node_id},
        )
        try:
            report = (
                asset_service.validate_runtime_year_map(path)
                if kind == "year_map"
                else asset_service.validate_runtime_model_library(path)
            )
        except Exception as exc:
            asset_service._remove_staged_file(path)
            raise ValueError(f"负荷 runtime 文件无法读取或校验：{exc}") from exc
        if not report.ok:
            asset_service._remove_staged_file(path)
            raise ValueError(asset_service._validation_failure_message([report], "负荷 runtime 文件校验未通过"))
        asset.metadata["validation"] = report.model_dump(mode="json")
        project.assets[asset.file_id] = asset

        opposite_kind = "model_library" if kind == "year_map" else "year_map"
        opposite_asset = next(
            (
                item
                for item in project.assets.values()
                if item.metadata.get("category") == "runtime"
                and item.metadata.get("subfolder") == node_id
                and item.metadata.get("runtime_kind") == opposite_kind
                and item.metadata.get("is_current")
            ),
            None,
        )

        bound = False
        if opposite_asset is not None:
            year_asset = asset if kind == "year_map" else opposite_asset
            model_asset = asset if kind == "model_library" else opposite_asset
            project, project_file = project_service.bind_runtime_assets(
                project_id=project_id,
                node_id=node_id,
                year_map_asset=year_asset,
                model_library_asset=model_asset,
            )
            bound = True
        else:
            asset.metadata["is_current"] = True
            _, project_file = project_service.save_project(project)

    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "project": project,
        "node_id": node_id,
        "kind": kind,
        "asset": asset,
        "report": report,
        "runtime_bound": bound,
        "project_file_path": str(project_file.resolve()),
    }


@router.post("/device-library/record/upsert", response_model=UpsertDeviceRecordResponse)
def upsert_device_record(request: UpsertDeviceRecordRequest) -> UpsertDeviceRecordResponse:
    try:
        project, project_file = project_service.upsert_device_record(
            project_id=request.project_id,
            record=request.record,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return UpsertDeviceRecordResponse(
        success=True,
        project=project,
        record=request.record,
        project_file_path=str(project_file.resolve()),
    )


@router.post("/device-library/record/delete", response_model=DeleteDeviceRecordResponse)
def delete_device_record(request: DeleteDeviceRecordRequest) -> DeleteDeviceRecordResponse:
    try:
        project, project_file = project_service.delete_device_record(
            project_id=request.project_id,
            vendor=request.vendor,
            model=request.model,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeleteDeviceRecordResponse(
        success=True,
        project=project,
        deleted_vendor=request.vendor,
        deleted_model=request.model,
        project_file_path=str(project_file.resolve()),
    )


@router.post("/raw-load-data/upload", response_model=RawLoadDataUploadResponse)
def upload_raw_load_data(
    project_id: str = Form(...),
    node_id: str = Form(...),
    file: UploadFile = File(...),
) -> RawLoadDataUploadResponse:
    """上传单个负荷节点的原始用电数据 Excel"""
    try:
        project_service.ensure_load_node(project_id, node_id)
        stored_path, file_name = processing_service.save_raw_load_data(
            project_id=project_id,
            node_id=node_id,
            file_content=file.file.read(),
            file_name=file.filename or "raw_load_data.xlsx",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RawLoadDataUploadResponse(
        success=True,
        node_id=node_id,
        file_name=file_name,
        stored_path=stored_path,
    )


@router.get("/raw-load-data/uploaded/{project_id}")
def list_uploaded_nodes(project_id: str) -> dict:
    """返回已上传原始数据的节点列表和已处理节点列表"""
    try:
        uploaded = processing_service.get_uploaded_nodes(project_id)
        processed = processing_service.get_processed_nodes(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "success": True,
        "project_id": project_id,
        "uploaded_nodes": uploaded,
        "processed_nodes": processed,
    }


@router.delete("/raw-load-data/{project_id}/{node_id}")
def delete_raw_load_data(project_id: str, node_id: str) -> dict:
    """删除某节点已上传的原始数据"""
    try:
        deleted = processing_service.delete_raw_load_data(project_id, node_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "project_id": project_id, "node_id": node_id, "deleted": deleted}


@router.post("/process-runtime")
async def process_runtime(request: ProcessRuntimeRequest):
    """一键批量处理——SSE 流式返回日志"""
    return StreamingResponse(
        processing_service.process_all_nodes(request.project_id, request.node_ids),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/preview/{project_id}/{node_id}")
def preview_node_files(project_id: str, node_id: str) -> PreviewNodeResponse:
    """列出某节点下所有可预览文件"""
    try:
        srv = LoadDataProcessingService(project_service=project_service)
        files = srv.list_preview_files(project_id, node_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    preview_files = [
        PreviewFileInfo(
            name=f["name"],
            type=f["type"],
            url=(
                f"/api/assets/preview/{quote(project_id, safe='')}/"
                f"{quote(node_id, safe='')}/{quote(f['name'], safe='')}"
            ),
        )
        for f in files
    ]
    return PreviewNodeResponse(node_id=node_id, files=preview_files)


@router.get("/preview/{project_id}/{node_id}/{file_name:path}")
def preview_file_content(project_id: str, node_id: str, file_name: str):
    """返回预览文件内容：图片 binary，CSV JSON 数组"""
    srv = LoadDataProcessingService(project_service=project_service)
    file_path = srv.get_preview_file_path(project_id, node_id, file_name)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在：{file_name}")

    suffix = file_path.suffix.lower()
    if suffix in PREVIEW_IMAGE_MEDIA_TYPES:
        return Response(
            content=file_path.read_bytes(),
            media_type=PREVIEW_IMAGE_MEDIA_TYPES[suffix],
            headers=PREVIEW_IMAGE_HEADERS,
        )
    elif suffix == ".csv":
        content = file_path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        return {"file_name": file_name, "columns": reader.fieldnames or [], "rows": rows, "total_rows": len(rows)}
    elif suffix == ".txt":
        content = file_path.read_text(encoding="utf-8")
        return {"file_name": file_name, "content": content}
    else:
        raise HTTPException(status_code=400, detail=f"不支持预览的文件类型：{suffix}")
