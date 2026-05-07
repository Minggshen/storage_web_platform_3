from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

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
from services.project_model_service import ProjectModelService


router = APIRouter(prefix="/api/assets", tags=["assets-binding"])

project_service = ProjectModelService()
asset_service = AssetBindingService(project_service=project_service)


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
        project, project_file = project_service.bind_runtime_assets(
            project_id=request.project_id,
            node_id=request.node_id,
            year_map_asset=year_asset,
            model_library_asset=model_asset,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    year_report = asset_service.validate_runtime_year_map(year_asset.metadata["stored_path"])
    model_report = asset_service.validate_runtime_model_library(model_asset.metadata["stored_path"])
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
        report = asset_service.validate_tariff_file(asset.metadata["stored_path"])
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
        asset, path, project, project_file = project_service.save_asset_upload(
            project_id=project_id,
            upload_file=file,
            category="runtime",
            subfolder=node_id,
            metadata={"runtime_kind": kind, "node_id": node_id},
        )
        report = (
            asset_service.validate_runtime_year_map(path)
            if kind == "year_map"
            else asset_service.validate_runtime_model_library(path)
        )
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
