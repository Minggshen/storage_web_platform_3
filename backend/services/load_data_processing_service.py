from __future__ import annotations

import asyncio
import traceback
from pathlib import Path
from typing import AsyncGenerator, Dict

from services.project_model_service import ProjectModelService


class LoadDataProcessingService:
    def __init__(self, project_service: ProjectModelService | None = None) -> None:
        self.project_service = project_service or ProjectModelService()

    def save_raw_load_data(
        self, project_id: str, node_id: str, file_content: bytes, file_name: str
    ) -> tuple[str, str]:
        """保存用户上传的原始负荷 Excel 到 raw_load_data/{node_id}/ 目录"""
        project_dir = self.project_service._project_dir(project_id)
        raw_dir = project_dir / "raw_load_data" / node_id
        raw_dir.mkdir(parents=True, exist_ok=True)

        target = raw_dir / "raw_load_data.xlsx"
        target.write_bytes(file_content)

        return str(target), "raw_load_data.xlsx"

    def get_uploaded_nodes(self, project_id: str) -> list[str]:
        """返回已上传原始数据（目录内确实有 xlsx 文件）的节点列表"""
        project_dir = self.project_service._project_dir(project_id)
        raw_root = project_dir / "raw_load_data"
        if not raw_root.exists():
            return []
        return sorted([
            d.name for d in raw_root.iterdir()
            if d.is_dir() and list(d.glob("*.xlsx"))
        ])

    def get_processed_nodes(self, project_id: str) -> list[str]:
        """返回已处理完成的节点列表（runtime CSV 已生成）"""
        project = self.project_service.load_project(project_id)
        processed: set = set()
        for asset in project.assets.values():
            meta = asset.metadata or {}
            if meta.get("category") == "runtime" and meta.get("is_current"):
                nid = str(meta.get("subfolder", ""))
                if nid:
                    processed.add(nid)
        return sorted(processed)

    async def process_all_nodes(
        self, project_id: str, node_ids: list[str]
    ) -> AsyncGenerator[str, None]:
        """逐节点批量处理，通过 async generator 推送 SSE 事件"""
        import json

        project = self.project_service.load_project(project_id)
        project_dir = self.project_service._project_dir(project_id)

        # 构建 node_id -> category 映射
        node_category: Dict[str, str] = {}
        for node in project.network.nodes:
            node_id_str = str(node.id)
            if node_id_str in node_ids:
                params = node.params if isinstance(node.params, dict) else {}
                cat = str(params.get("category", "industrial")).lower()
                node_category[node_id_str] = cat

        yield f"data: {json.dumps({'type': 'start', 'total': len(node_ids)}, ensure_ascii=False)}\n\n"

        success = 0
        failed = 0

        for idx, node_id in enumerate(node_ids):
            cat = node_category.get(node_id, "industrial")
            raw_dir = project_dir / "raw_load_data" / node_id
            runtime_dir = project_dir / "assets" / "runtime" / node_id
            model_dir = project_dir / "modeling_output" / node_id
            runtime_dir.mkdir(parents=True, exist_ok=True)
            model_dir.mkdir(parents=True, exist_ok=True)

            try:
                yield f"data: {json.dumps({'type': 'progress', 'node': node_id, 'step': 'modeling', 'message': f'开始建模（类型={cat}）...', 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 找到 raw_dir 下的实际 xlsx 文件
                xlsx_files = sorted(raw_dir.glob("*.xlsx"))
                if not xlsx_files:
                    raise FileNotFoundError(f"目录 {raw_dir} 下未找到任何 xlsx 文件")
                raw_file = xlsx_files[0]

                # 1. 建模
                if cat == "residential":
                    from services.load_modeling_residential import process_raw_data as model_residential
                    result = model_residential(raw_file, str(model_dir))
                else:
                    from services.load_modeling_industrial import process_raw_data as model_industrial
                    result = model_industrial(raw_file, str(model_dir))

                yield f"data: {json.dumps({'type': 'progress', 'node': node_id, 'step': 'convert', 'message': '建模完成，开始生成 runtime CSV...', 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 2. 转换
                if cat == "residential":
                    from services.build_runtime_residential import process_one_node as build_residential
                    build_result = build_residential(str(model_dir), str(runtime_dir))
                else:
                    from services.build_runtime_industrial import process_one_node as build_industrial
                    build_result = build_industrial(str(model_dir), str(runtime_dir))

                # 3. 注册到 project.assets
                ym_path = Path(build_result["year_map_path"])
                ml_path = Path(build_result["model_library_path"])

                ym_asset, project, _ = self.project_service.register_asset_file(
                    project_id=project_id,
                    file_path=ym_path,
                    category="runtime",
                    subfolder=node_id,
                    metadata={"runtime_kind": "year_map", "node_id": node_id},
                )
                ml_asset, project, _ = self.project_service.register_asset_file(
                    project_id=project_id,
                    file_path=ml_path,
                    category="runtime",
                    subfolder=node_id,
                    metadata={"runtime_kind": "model_library", "node_id": node_id},
                )

                # 4. 绑定到拓扑节点
                project, _ = self.project_service.bind_runtime_assets(
                    project_id=project_id,
                    node_id=node_id,
                    year_map_asset=ym_asset,
                    model_library_asset=ml_asset,
                )
                project.assets[ym_asset.file_id] = ym_asset
                project.assets[ml_asset.file_id] = ml_asset
                self.project_service.save_project(project)

                success += 1
                charts = result.get("charts", [])
                yield f"data: {json.dumps({'type': 'done', 'node': node_id, 'charts': charts, 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"

            except Exception as exc:
                failed += 1
                tb = traceback.format_exc()
                yield f"data: {json.dumps({'type': 'error', 'node': node_id, 'message': str(exc), 'traceback': tb, 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"

            await asyncio.sleep(0)

        yield f"data: {json.dumps({'type': 'complete', 'total': len(node_ids), 'success': success, 'failed': failed}, ensure_ascii=False)}\n\n"

    def delete_raw_load_data(self, project_id: str, node_id: str) -> bool:
        """删除某节点的原始上传数据及建模产物"""
        import shutil

        project_dir = self.project_service._project_dir(project_id)
        deleted = False

        raw_dir = project_dir / "raw_load_data" / node_id
        if raw_dir.exists():
            shutil.rmtree(str(raw_dir))
            deleted = True

        model_dir = project_dir / "modeling_output" / node_id
        if model_dir.exists():
            shutil.rmtree(str(model_dir))
            deleted = True

        return deleted

    def list_preview_files(self, project_id: str, node_id: str) -> list[dict]:
        """列出某节点下所有可预览文件（PNG + CSV + TXT）"""
        project_dir = self.project_service._project_dir(project_id)
        model_dir = project_dir / "modeling_output" / node_id
        runtime_dir = project_dir / "assets" / "runtime" / node_id

        files = []
        for d in [model_dir, runtime_dir]:
            if not d.exists():
                continue
            for f in sorted(d.rglob("*")):
                if not f.is_file():
                    continue
                if f.suffix.lower() == ".png":
                    files.append({"name": f.name, "type": "image"})
                elif f.suffix.lower() == ".csv":
                    files.append({"name": f.name, "type": "csv"})
                elif f.suffix.lower() == ".txt":
                    files.append({"name": f.name, "type": "text"})

        return files

    def get_preview_file_path(self, project_id: str, node_id: str, file_name: str) -> Path | None:
        """获取预览文件的完整路径"""
        project_dir = self.project_service._project_dir(project_id)
        model_base = project_dir / "modeling_output" / node_id
        runtime_base = project_dir / "assets" / "runtime" / node_id
        for base in [model_base, runtime_base]:
            if not base.exists():
                continue
            for p in base.rglob(file_name):
                if p.is_file():
                    return p
        return None

    @staticmethod
    def cleanup_empty_dirs(project_id: str, project_service: ProjectModelService | None = None) -> dict:
        """一次性清理工程中所有的空目录残留"""
        import shutil

        ps = project_service or ProjectModelService()
        project_dir = ps._project_dir(project_id)

        removed = []

        def _rm_if_empty(p: Path) -> bool:
            if p.exists() and p.is_dir() and not any(p.iterdir()):
                p.rmdir()
                return True
            return False

        def _rm_tree_if_empty(p: Path) -> bool:
            if not p.exists() or not p.is_dir():
                return False
            has_content = any(
                f.is_file() or (f.is_dir() and any(f.iterdir()))
                for f in p.rglob("*")
            )
            if not has_content:
                shutil.rmtree(str(p))
                return True
            return False

        # 1) raw_load_data/*/raw_load_data/ —— 旧代码空子目录
        raw_root = project_dir / "raw_load_data"
        if raw_root.exists():
            for node_dir in raw_root.iterdir():
                if not node_dir.is_dir():
                    continue
                nested = node_dir / "raw_load_data"
                if _rm_if_empty(nested):
                    removed.append(str(nested.relative_to(project_dir)))

        # 2) assets/runtime/*/ —— 空节点目录
        runtime_root = project_dir / "assets" / "runtime"
        if runtime_root.exists():
            for node_dir in runtime_root.iterdir():
                if not node_dir.is_dir():
                    continue
                if _rm_if_empty(node_dir):
                    removed.append(str(node_dir.relative_to(project_dir)))

        # 3) build/solver_workspace/inputs/node_loads/ —— 空目录树
        nl_root = project_dir / "build" / "solver_workspace" / "inputs" / "node_loads"
        if nl_root.exists():
            for cat_dir in nl_root.iterdir():
                if not cat_dir.is_dir():
                    continue
                for node_dir in cat_dir.iterdir():
                    if node_dir.is_dir() and _rm_if_empty(node_dir):
                        removed.append(str(node_dir.relative_to(project_dir)))
                if _rm_if_empty(cat_dir):
                    removed.append(str(cat_dir.relative_to(project_dir)))
            if _rm_if_empty(nl_root):
                removed.append(str(nl_root.relative_to(project_dir)))

        # 4) build/solver_workspace/inputs/{tariff,storage}/ —— 空
        for sub in ["tariff", "storage"]:
            d = project_dir / "build" / "solver_workspace" / "inputs" / sub
            if _rm_if_empty(d):
                removed.append(str(d.relative_to(project_dir)))

        # 5) build/solver_workspace/outputs/ —— 空
        out_d = project_dir / "build" / "solver_workspace" / "outputs"
        if _rm_tree_if_empty(out_d):
            removed.append(str(out_d.relative_to(project_dir)))

        return {"project_id": project_id, "removed": removed}
