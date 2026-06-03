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


def test_spa_static_path_containment_rejects_prefix_sibling() -> None:
    from storage_fastapi_backend import _is_within_static_root, _static_root  # noqa: PLC0415

    sibling = _static_root.parent / f"{_static_root.name}_sibling" / "index.html"
    assert _is_within_static_root(_static_root / "index.html") is True
    assert _is_within_static_root(sibling) is False
