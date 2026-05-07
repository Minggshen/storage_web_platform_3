
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import UploadFile

from models.project_model import AssetRef, DeviceRecord, ListProjectsItem, NetworkEdge, NetworkModel, NetworkNode, ProjectModel, SolverBindingConfig

PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


class ProjectModelService:
    """Persist and update visual-modeling project JSON files and project assets."""

    def __init__(self, base_dir: str | Path = "data/projects") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _model_dump(model: ProjectModel) -> dict:
        if hasattr(model, "model_dump"):
            return model.model_dump(mode="json")
        return model.dict()

    def _project_dir(self, project_id: str) -> Path:
        return self.base_dir / project_id

    def _project_dir_for_delete(self, project_id: str) -> Path:
        project_id = str(project_id or "").strip()
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ValueError(f"项目编号格式非法：{project_id}")

        base_dir = self.base_dir.resolve()
        project_dir = (base_dir / project_id).resolve()
        if project_dir == base_dir or base_dir not in project_dir.parents:
            raise ValueError("项目路径越界，已拒绝删除。")
        return project_dir

    def _project_file(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def _assets_dir(self, project_id: str) -> Path:
        path = self._project_dir(project_id) / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def generate_project_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def generate_asset_id(self) -> str:
        return f"asset_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _format_timestamp(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _parse_project_time(value: str) -> float:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def _project_created_at(self, raw: dict, project_file: Path) -> str:
        value = raw.get("created_at")
        if isinstance(value, str) and value.strip():
            return value.strip()

        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            metadata_value = metadata.get("created_at")
            if isinstance(metadata_value, str) and metadata_value.strip():
                return metadata_value.strip()

        try:
            return self._format_timestamp(project_file.stat().st_ctime)
        except OSError:
            return self._now_iso()

    def create_empty_project(self, project_name: str, description: str | None = None) -> tuple[ProjectModel, Path]:
        project = ProjectModel(project_name=project_name.strip(), description=description)
        project_id, project_file = self.save_project(project)
        project.project_id = project_id
        return project, project_file

    def save_project(self, project: ProjectModel) -> tuple[str, Path]:
        project_id = project.project_id or self.generate_project_id()
        project.project_id = project_id

        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        project_file = self._project_file(project_id)
        if not project.created_at:
            project.created_at = self._format_timestamp(project_file.stat().st_ctime) if project_file.exists() else self._now_iso()

        data = self._model_dump(project)
        project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return project_id, project_file

    def load_project(self, project_id: str) -> ProjectModel:
        project_file = self._project_file(project_id)
        if not project_file.exists():
            raise FileNotFoundError(f"项目不存在：{project_id}")
        raw = json.loads(project_file.read_text(encoding="utf-8"))
        return ProjectModel(**raw)

    def list_projects(self) -> List[ListProjectsItem]:
        items: List[ListProjectsItem] = []
        if not self.base_dir.exists():
            return items

        for project_file in sorted(self.base_dir.glob("*/project.json")):
            try:
                raw = json.loads(project_file.read_text(encoding="utf-8"))
                created_at = self._project_created_at(raw, project_file)
                project = ProjectModel(**raw)
                items.append(
                    ListProjectsItem(
                        project_id=project.project_id or project_file.parent.name,
                        project_name=project.project_name,
                        created_at=created_at,
                        project_file_path=str(project_file.resolve()),
                    )
                )
            except Exception:
                continue

        items.sort(key=lambda item: self._parse_project_time(item.created_at), reverse=True)
        return items

    def list_assets(self, project_id: str) -> List[AssetRef]:
        project = self.load_project(project_id)
        return list(project.assets.values())

    def upsert_node(self, project_id: str, node: NetworkNode) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        replaced = False
        new_nodes: List[NetworkNode] = []
        for existing in project.network.nodes:
            if existing.id == node.id:
                new_nodes.append(node)
                replaced = True
            else:
                new_nodes.append(existing)
        if not replaced:
            new_nodes.append(node)
        project.network.nodes = new_nodes
        _, project_file = self.save_project(project)
        return project, project_file

    def delete_node(self, project_id: str, node_id: str) -> tuple[ProjectModel, Path, List[str]]:
        project = self.load_project(project_id)
        original_node_count = len(project.network.nodes)
        project.network.nodes = [node for node in project.network.nodes if node.id != node_id]
        if len(project.network.nodes) == original_node_count:
            raise FileNotFoundError(f"节点不存在：{node_id}")

        deleted_edge_ids = [edge.id for edge in project.network.edges if edge.from_node_id == node_id or edge.to_node_id == node_id]
        project.network.edges = [
            edge for edge in project.network.edges if edge.from_node_id != node_id and edge.to_node_id != node_id
        ]
        _, project_file = self.save_project(project)
        return project, project_file, deleted_edge_ids

    def upsert_edge(self, project_id: str, edge: NetworkEdge) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        replaced = False
        new_edges: List[NetworkEdge] = []
        for existing in project.network.edges:
            if existing.id == edge.id:
                new_edges.append(edge)
                replaced = True
            else:
                new_edges.append(existing)
        if not replaced:
            new_edges.append(edge)
        project.network.edges = new_edges
        _, project_file = self.save_project(project)
        return project, project_file

    def delete_edge(self, project_id: str, edge_id: str) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        original_edge_count = len(project.network.edges)
        project.network.edges = [edge for edge in project.network.edges if edge.id != edge_id]
        if len(project.network.edges) == original_edge_count:
            raise FileNotFoundError(f"线路不存在：{edge_id}")
        _, project_file = self.save_project(project)
        return project, project_file

    def ensure_load_node(self, project_id: str, node_id: str) -> NetworkNode:
        project = self.load_project(project_id)
        for node in project.network.nodes:
            if node.id == node_id:
                if str(node.type.value) != "load":
                    raise ValueError(f"节点 {node_id} 不是负荷节点，不能绑定 runtime 文件")
                return node
        raise FileNotFoundError(f"负荷节点不存在：{node_id}")

    def save_asset_upload(
        self,
        project_id: str,
        upload_file: UploadFile,
        category: str,
        subfolder: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[AssetRef, Path, ProjectModel, Path]:
        project = self.load_project(project_id)
        asset_id = self.generate_asset_id()
        original_name = upload_file.filename or f"{asset_id}.bin"
        safe_name = Path(original_name).name
        asset_dir = self._assets_dir(project_id) / category
        if subfolder:
            asset_dir = asset_dir / subfolder
        asset_dir.mkdir(parents=True, exist_ok=True)

        target_file = asset_dir / f"{asset_id}_{safe_name}"
        upload_file.file.seek(0)
        with target_file.open("wb") as f:
            shutil.copyfileobj(upload_file.file, f)

        asset = AssetRef(
            file_id=asset_id,
            file_name=safe_name,
            source_type="upload",
            metadata={
                "category": category,
                "subfolder": subfolder,
                "stored_path": str(target_file.resolve()),
                **(metadata or {}),
            },
        )
        project.assets[asset_id] = asset
        _, project_file = self.save_project(project)
        return asset, target_file, project, project_file

    def get_asset(self, project: ProjectModel, file_id: str) -> AssetRef:
        asset = project.assets.get(file_id)
        if asset is None:
            raise FileNotFoundError(f"资产不存在：{file_id}")
        return asset

    def _mark_current_asset(self, project: ProjectModel, category: str, current_file_id: str, *, subfolder: str | None = None, runtime_kind: str | None = None) -> None:
        for asset in project.assets.values():
            if asset.metadata.get("category") != category:
                continue
            if subfolder is not None and asset.metadata.get("subfolder") != subfolder:
                continue
            if runtime_kind is not None and asset.metadata.get("runtime_kind") != runtime_kind:
                continue
            asset.metadata["is_current"] = asset.file_id == current_file_id

    def bind_runtime_assets(self, project_id: str, node_id: str, year_map_asset: AssetRef, model_library_asset: AssetRef) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        bound = False
        for node in project.network.nodes:
            if node.id == node_id:
                if str(node.type.value) != "load":
                    raise ValueError(f"节点 {node_id} 不是负荷节点，不能绑定 runtime 文件")
                if node.runtime_binding is None:
                    from models.project_model import RuntimeBinding
                    node.runtime_binding = RuntimeBinding()
                node.runtime_binding.year_map_file_id = year_map_asset.file_id
                node.runtime_binding.year_map_file_name = year_map_asset.file_name
                node.runtime_binding.model_library_file_id = model_library_asset.file_id
                node.runtime_binding.model_library_file_name = model_library_asset.file_name
                bound = True
                break
        if not bound:
            raise FileNotFoundError(f"负荷节点不存在：{node_id}")
        project.assets[year_map_asset.file_id] = year_map_asset
        project.assets[model_library_asset.file_id] = model_library_asset
        self._mark_current_asset(project, "runtime", year_map_asset.file_id, subfolder=node_id, runtime_kind="year_map")
        self._mark_current_asset(project, "runtime", model_library_asset.file_id, subfolder=node_id, runtime_kind="model_library")
        _, project_file = self.save_project(project)
        return project, project_file

    def bind_tariff_asset(self, project_id: str, asset: AssetRef, tariff_year: int | None = None) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        project.tariff.asset = asset
        if tariff_year is not None:
            project.tariff.tariff_year = tariff_year
        project.assets[asset.file_id] = asset
        self._mark_current_asset(project, "tariff", asset.file_id)
        _, project_file = self.save_project(project)
        return project, project_file

    def replace_device_library(self, project_id: str, asset: AssetRef, records: List[DeviceRecord]) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        project.device_library.asset = asset
        project.device_library.records = records
        project.assets[asset.file_id] = asset
        self._mark_current_asset(project, "device_library", asset.file_id)
        _, project_file = self.save_project(project)
        return project, project_file

    def upsert_device_record(self, project_id: str, record: DeviceRecord) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        replaced = False
        records: List[DeviceRecord] = []
        for existing in project.device_library.records:
            if existing.vendor.strip() == record.vendor.strip() and existing.model.strip() == record.model.strip():
                records.append(record)
                replaced = True
            else:
                records.append(existing)
        if not replaced:
            records.append(record)
        project.device_library.records = records
        _, project_file = self.save_project(project)
        return project, project_file

    def delete_device_record(self, project_id: str, vendor: str, model: str) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        before = len(project.device_library.records)
        project.device_library.records = [
            item for item in project.device_library.records
            if not (item.vendor.strip() == vendor.strip() and item.model.strip() == model.strip())
        ]
        if len(project.device_library.records) == before:
            raise FileNotFoundError(f"设备记录不存在：{vendor}/{model}")
        _, project_file = self.save_project(project)
        return project, project_file


    def update_solver_binding(self, project_id: str, solver_binding: SolverBindingConfig) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        project.solver_binding = solver_binding
        project.solver_binding.enabled = True
        _, project_file = self.save_project(project)
        return project, project_file


    def replace_topology(self, project_id: str, network: NetworkModel) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        project.network = network
        _, project_file = self.save_project(project)
        return project, project_file

    def delete_project(self, project_id: str) -> Path:
        project_dir = self._project_dir_for_delete(project_id)
        if not project_dir.exists() or not project_dir.is_dir():
            raise FileNotFoundError(f"项目不存在：{project_id}")
        if not (project_dir / "project.json").is_file():
            raise ValueError("目标目录缺少 project.json，已拒绝删除。")

        for item in project_dir.rglob("*"):
            if item.is_symlink():
                raise ValueError(f"项目目录中存在符号链接，已拒绝删除：{item.name}")
            resolved = item.resolve()
            if resolved != project_dir and project_dir not in resolved.parents:
                raise ValueError("项目目录中存在越界路径，已拒绝删除。")

        shutil.rmtree(project_dir)
        return project_dir

    def clone_project(self, project_id: str, new_project_name: str | None = None) -> tuple[ProjectModel, Path]:
        project = self.load_project(project_id)
        new_project_id = self.generate_project_id()
        cloned = ProjectModel(**self._model_dump(project))
        cloned.project_id = new_project_id
        if new_project_name:
            cloned.project_name = new_project_name.strip()
        else:
            cloned.project_name = f"{project.project_name}_副本"
        cloned.created_at = None
        target_dir = self._project_dir(new_project_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        # clone assets folder if exists
        source_assets = self._assets_dir(project_id)
        if source_assets.exists():
            target_assets = target_dir / "assets"
            shutil.copytree(source_assets, target_assets, dirs_exist_ok=True)
        _, project_file = self.save_project(cloned)
        return cloned, project_file
