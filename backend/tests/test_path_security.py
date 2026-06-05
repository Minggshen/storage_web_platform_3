from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

sys.modules.pop("services.project_model_service", None)
sys.modules.pop("services.load_data_processing_service", None)

from services.load_data_processing_service import LoadDataProcessingService  # noqa: E402
from services.project_model_service import ProjectModelService  # noqa: E402


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
