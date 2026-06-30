from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

sys.modules.pop("services.project_model_service", None)
sys.modules.pop("services.load_data_processing_service", None)

from models.project_model import AssetRef, DeviceRecord  # noqa: E402
from services import file_store  # noqa: E402
from services.asset_binding_service import AssetBindingService  # noqa: E402
from services.atomic_io import write_bytes_atomic, write_text_atomic  # noqa: E402
from services.build_export_service import BuildExportService  # noqa: E402
from services.build_inference_service import BuildInferenceService  # noqa: E402
from services.file_store import extract_zip_if_needed  # noqa: E402
from services.load_data_processing_service import LoadDataProcessingService  # noqa: E402
from services.project_model_service import ProjectModelService  # noqa: E402
from routes import assets as assets_routes  # noqa: E402


def test_project_dir_rejects_path_traversal(tmp_path: Path) -> None:
    service = ProjectModelService(base_dir=tmp_path)

    with pytest.raises(FileNotFoundError):
        service._project_dir("../escape")
    with pytest.raises(FileNotFoundError):
        service._project_dir("..\\escape")


def test_asset_subfolder_rejects_path_traversal(tmp_path: Path) -> None:
    service = ProjectModelService(base_dir=tmp_path)

    with pytest.raises(ValueError):
        service.safe_path_segment("../escape", "资产子目录")
    with pytest.raises(ValueError):
        service.safe_path_segment("..\\escape", "资产子目录")


def test_load_preview_rejects_unsafe_node_and_file_name(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    processing = LoadDataProcessingService(project_service=project_service)
    project_id = "abc123"
    (tmp_path / project_id / "project.json").parent.mkdir(parents=True)

    with pytest.raises(ValueError):
        processing.get_preview_file_path(project_id, "../node", "x.csv")
    with pytest.raises(ValueError):
        processing.get_preview_file_path(project_id, "node01", "../x.csv")


def test_load_preview_does_not_return_symlinked_file(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    processing = LoadDataProcessingService(project_service=project_service)
    project_id = "abc123"
    node_id = "node01"
    model_dir = tmp_path / project_id / "modeling_output" / node_id
    model_dir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = model_dir / "outside.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"当前系统不允许创建符号链接：{exc}")

    assert processing.get_preview_file_path(project_id, node_id, "outside.txt") is None


def test_load_preview_lists_svg_and_legacy_png_images(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    processing = LoadDataProcessingService(project_service=project_service)
    project_id = "abc123"
    node_id = "node01"
    model_dir = tmp_path / project_id / "modeling_output" / node_id
    model_dir.mkdir(parents=True)
    (model_dir / "model.svg").write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" />", encoding="utf-8")
    (model_dir / "legacy.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (model_dir / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    files = processing.list_preview_files(project_id, node_id)

    assert {"name": "model.svg", "type": "image"} in files
    assert {"name": "legacy.png", "type": "image"} in files
    assert {"name": "data.csv", "type": "csv"} in files
    assert processing.get_preview_file_path(project_id, node_id, "model.svg") == model_dir / "model.svg"


def test_delete_raw_load_data_removes_only_selected_node(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    processing = LoadDataProcessingService(project_service=project_service)
    project_id = "abc123"
    project_dir = tmp_path / project_id
    selected_raw = project_dir / "raw_load_data" / "node01"
    sibling_raw = project_dir / "raw_load_data" / "node02"
    selected_model = project_dir / "modeling_output" / "node01"
    selected_raw.mkdir(parents=True)
    sibling_raw.mkdir(parents=True)
    selected_model.mkdir(parents=True)
    (selected_raw / "raw_load_data.xlsx").write_text("raw", encoding="utf-8")
    (sibling_raw / "raw_load_data.xlsx").write_text("keep", encoding="utf-8")
    (selected_model / "model.svg").write_text("<svg />", encoding="utf-8")

    assert processing.delete_raw_load_data(project_id, "node01") is True

    assert not selected_raw.exists()
    assert not selected_model.exists()
    assert (sibling_raw / "raw_load_data.xlsx").exists()


def test_load_modeling_process_raw_data_reports_svg_charts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sklearn")
    pytest.importorskip("matplotlib")
    from services import load_modeling_industrial, load_modeling_residential  # noqa: PLC0415

    raw_file = tmp_path / "raw.xlsx"
    raw_file.write_text("placeholder", encoding="utf-8")

    def fake_process_one_company(file_path: Path, output_root: Path) -> None:
        nested_dir = output_root / file_path.stem
        nested_dir.mkdir(parents=True)
        (nested_dir / "01_预览图.svg").write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" />", encoding="utf-8")
        (nested_dir / "01_旧图.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (nested_dir / "01_模型.xlsx").write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(load_modeling_industrial, "process_one_company", fake_process_one_company)
    monkeypatch.setattr(load_modeling_residential, "process_one_company", fake_process_one_company)

    industrial_result = load_modeling_industrial.process_raw_data(raw_file, tmp_path / "industrial")
    residential_result = load_modeling_residential.process_raw_data(raw_file, tmp_path / "residential")

    assert industrial_result["charts"] == ["01_预览图.svg"]
    assert residential_result["charts"] == ["01_预览图.svg"]


def test_spa_static_path_containment_rejects_prefix_sibling() -> None:
    from storage_fastapi_backend import _is_within_static_root, _static_root  # noqa: PLC0415

    sibling = _static_root.parent / f"{_static_root.name}_sibling" / "index.html"
    assert _is_within_static_root(_static_root / "index.html") is True
    assert _is_within_static_root(sibling) is False


def test_extract_zip_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    escaped_name = f"../{tmp_path.name}_escaped.txt"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(escaped_name, "bad")

    with pytest.raises(HTTPException) as exc_info:
        extract_zip_if_needed(zip_path)

    assert exc_info.value.status_code == 400
    assert not (tmp_path.parent / f"{tmp_path.name}_escaped.txt").exists()


def test_extract_zip_accepts_nested_safe_paths(tmp_path: Path) -> None:
    zip_path = tmp_path / "safe.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("nested/data.txt", "ok")

    extract_dir = extract_zip_if_needed(zip_path)

    assert (extract_dir / "nested" / "data.txt").read_text(encoding="utf-8") == "ok"


def test_extract_zip_rejects_uncompressed_size_over_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    zip_path = tmp_path / "too_large.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data.txt", "0123456789")

    monkeypatch.setattr(file_store, "MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES", 5)

    with pytest.raises(HTTPException) as exc_info:
        extract_zip_if_needed(zip_path)

    assert exc_info.value.status_code == 400
    assert not (tmp_path / "too_large" / "data.txt").exists()


def test_atomic_writes_replace_content_and_clear_temp_files(tmp_path: Path) -> None:
    text_path = tmp_path / "project.json"
    bytes_path = tmp_path / "raw.xlsx"

    write_text_atomic(text_path, "old", encoding="utf-8")
    write_text_atomic(text_path, "new", encoding="utf-8")
    write_bytes_atomic(bytes_path, b"xlsx")

    assert text_path.read_text(encoding="utf-8") == "new"
    assert bytes_path.read_bytes() == b"xlsx"
    assert not list(tmp_path.glob(".*.tmp"))


def test_clone_project_rewrites_asset_paths_to_clone_directory(tmp_path: Path) -> None:
    service = ProjectModelService(base_dir=tmp_path)
    project, _ = service.create_empty_project("source")
    assert project.project_id is not None

    source_project_dir = service._project_dir(project.project_id)
    source_asset_dir = source_project_dir / "assets" / "tariff"
    source_asset_dir.mkdir(parents=True)
    source_asset = source_asset_dir / "asset_001_price.xlsx"
    source_asset.write_text("price", encoding="utf-8")

    asset = AssetRef(
        file_id="asset_001",
        file_name="price.xlsx",
        source_type="upload",
        metadata={"category": "tariff", "stored_path": str(source_asset.resolve())},
    )
    project.assets[asset.file_id] = asset
    project.tariff.asset = asset
    service.save_project(project)

    cloned, _ = service.clone_project(project.project_id, "copy")
    assert cloned.project_id is not None
    cloned_asset_path = Path(str(cloned.assets["asset_001"].metadata["stored_path"]))

    assert source_project_dir not in cloned_asset_path.resolve().parents
    assert service._project_dir(cloned.project_id) in cloned_asset_path.resolve().parents
    assert cloned_asset_path.read_text(encoding="utf-8") == "price"
    assert cloned.tariff.asset is not None
    assert cloned.tariff.asset.metadata["stored_path"] == str(cloned_asset_path.resolve())


def test_invalid_tariff_upload_does_not_bind_project_asset(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    project, _ = project_service.create_empty_project("source")
    assert project.project_id is not None

    asset_service = AssetBindingService(project_service=project_service)
    bad_upload = UploadFile(file=io.BytesIO(b"not an excel workbook"), filename="tariff.xls")

    with pytest.raises(ValueError, match="文件格式不支持"):
        asset_service.upload_tariff_file(project.project_id, bad_upload)

    reloaded = project_service.load_project(project.project_id)
    assert reloaded.tariff.asset is None
    assert reloaded.assets == {}


def test_replace_device_library_keeps_only_current_upload_file(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    project, _ = project_service.create_empty_project("source")
    assert project.project_id is not None

    device_dir = tmp_path / project.project_id / "assets" / "device_library"
    device_dir.mkdir(parents=True)
    old_path = device_dir / "asset_old_工商业储能设备策略库.xlsx"
    orphan_path = device_dir / "asset_orphan_工商业储能设备策略库.xlsx"
    keep_path = device_dir / "asset_new_工商业储能设备策略库_v2模板.xlsx"
    note_path = device_dir / "manual_note.txt"
    old_path.write_bytes(b"old")
    orphan_path.write_bytes(b"orphan")
    keep_path.write_bytes(b"new")
    note_path.write_text("keep local note", encoding="utf-8")

    old_asset = AssetRef(
        file_id="asset_old",
        file_name="工商业储能设备策略库.xlsx",
        source_type="upload",
        metadata={"category": "device_library", "stored_path": str(old_path.resolve()), "is_current": True},
    )
    new_asset = AssetRef(
        file_id="asset_new",
        file_name="工商业储能设备策略库_v2模板.xlsx",
        source_type="upload",
        metadata={"category": "device_library", "stored_path": str(keep_path.resolve())},
    )
    project.assets[old_asset.file_id] = old_asset
    project.device_library.asset = old_asset
    project_service.save_project(project)

    project_service.replace_device_library(
        project.project_id,
        new_asset,
        [DeviceRecord(vendor="测试厂商", model="SafeBox-100")],
    )

    reloaded = project_service.load_project(project.project_id)
    assert reloaded.device_library.asset is not None
    assert reloaded.device_library.asset.file_id == "asset_new"
    assert "device_library_cleanup_failures" not in reloaded.metadata
    assert "asset_old" not in reloaded.assets
    assert "asset_new" in reloaded.assets
    assert old_path.exists() is False
    assert orphan_path.exists() is False
    assert keep_path.exists() is True
    assert note_path.exists() is True


def test_build_asset_path_rejects_files_outside_project_assets(tmp_path: Path) -> None:
    project_dir = tmp_path / "abc123"
    project_dir.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("secret", encoding="utf-8")

    asset = {"metadata": {"stored_path": str(outside.resolve())}}
    service = BuildExportService(data_root=tmp_path)

    assert service._asset_path(asset, project_dir=project_dir) is None


def test_route_asset_bind_path_must_stay_inside_project_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    monkeypatch.setattr(assets_routes, "project_service", project_service)
    project_dir = tmp_path / "abc123"
    assets_dir = project_dir / "assets" / "runtime"
    assets_dir.mkdir(parents=True)
    inside = assets_dir / "ok.csv"
    outside = tmp_path / "outside.csv"
    inside.write_text("ok", encoding="utf-8")
    outside.write_text("secret", encoding="utf-8")

    assert assets_routes._project_asset_file_path("abc123", str(inside.resolve())) == inside.resolve()
    with pytest.raises(ValueError, match="不在当前项目 assets 目录"):
        assets_routes._project_asset_file_path("abc123", str(outside.resolve()))


def test_build_signature_marks_asset_outside_project_without_stat(tmp_path: Path) -> None:
    project_dir = tmp_path / "abc123"
    assets_dir = project_dir / "assets" / "tariff"
    assets_dir.mkdir(parents=True)
    outside = tmp_path / "outside.xlsx"
    outside.write_text("secret", encoding="utf-8")

    service = BuildExportService(data_root=tmp_path)
    signature = service._build_input_signature(
        {
            "project_id": "abc123",
            "network": {"nodes": [], "edges": [], "economic_parameters": {}},
            "tariff": {
                "asset": {
                    "file_id": "asset_001",
                    "file_name": "outside.xlsx",
                    "source_type": "upload",
                    "metadata": {"stored_path": str(outside.resolve())},
                }
            },
        }
    )

    file_stat = signature["tariff"]["asset"]["file_stat"]
    assert file_stat["outside_project_assets"] is True
    assert "size" not in file_stat


def test_build_inference_ignores_runtime_assets_outside_project_assets(tmp_path: Path) -> None:
    project_service = ProjectModelService(base_dir=tmp_path)
    project, _ = project_service.create_empty_project("source")
    assert project.project_id is not None

    outside_year = tmp_path / "outside_year.csv"
    outside_model = tmp_path / "outside_model.csv"
    outside_year.write_text("internal_model_id\nM1\n", encoding="utf-8")
    outside_model.write_text(
        "internal_model_id,h00,h01,h02,h03,h04,h05,h06,h07,h08,h09,h10,h11,h12,h13,h14,h15,h16,h17,h18,h19,h20,h21,h22,h23\n"
        "M1,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999,999\n",
        encoding="utf-8",
    )

    year_asset = AssetRef(
        file_id="year",
        file_name="year.csv",
        source_type="upload",
        metadata={"category": "runtime", "stored_path": str(outside_year.resolve())},
    )
    model_asset = AssetRef(
        file_id="model",
        file_name="model.csv",
        source_type="upload",
        metadata={"category": "runtime", "stored_path": str(outside_model.resolve())},
    )
    project.assets[year_asset.file_id] = year_asset
    project.assets[model_asset.file_id] = model_asset
    service = BuildInferenceService(project_service=project_service)
    node = SimpleNamespace(
        runtime_binding=SimpleNamespace(year_map_file_id=year_asset.file_id, model_library_file_id=model_asset.file_id)
    )

    assert service._load_runtime_stats(project, node) == {}
