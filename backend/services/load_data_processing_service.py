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

        target = raw_dir / file_name
        target.write_bytes(file_content)

        return str(target), file_name

    def get_uploaded_nodes(self, project_id: str) -> list[str]:
        """返回已上传原始数据但尚未处理的节点列表"""
        project_dir = self.project_service._project_dir(project_id)
        raw_root = project_dir / "raw_load_data"
        if not raw_root.exists():
            return []
        return sorted(
            [d.name for d in raw_root.iterdir() if d.is_dir()]
        )

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
            runtime_dir.mkdir(parents=True, exist_ok=True)

            try:
                yield f"data: {json.dumps({'type': 'progress', 'node': node_id, 'step': 'modeling', 'message': f'开始建模（类型={cat}）...', 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 1. 建模
                if cat == "residential":
                    from scripts.全年逐日典型日聚类1h级居民负荷建模 import process_raw_data as model_residential
                    result = model_residential(
                        str(raw_dir / "raw_load_data.xlsx"),
                        str(raw_dir),
                    )
                else:
                    from scripts.按工休和年用电峰谷分析的1h级工商业负荷建模_改 import process_raw_data as model_industrial
                    result = model_industrial(
                        str(raw_dir / "raw_load_data.xlsx"),
                        str(raw_dir),
                    )

                yield f"data: {json.dumps({'type': 'progress', 'node': node_id, 'step': 'convert', 'message': '建模完成，开始生成 runtime CSV...', 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 2. 转换
                if cat == "residential":
                    from scripts.build_runtime_files_residential import process_one_node as build_residential
                    build_result = build_residential(str(raw_dir), str(runtime_dir))
                else:
                    from scripts.build_runtime_files_industrial_or_commercial import process_one_node as build_industrial
                    build_result = build_industrial(str(raw_dir), str(runtime_dir))

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

    def list_preview_files(self, project_id: str, node_id: str) -> list[dict]:
        """列出某节点下所有可预览文件（PNG + CSV + TXT）"""
        project_dir = self.project_service._project_dir(project_id)
        raw_dir = project_dir / "raw_load_data" / node_id
        runtime_dir = project_dir / "assets" / "runtime" / node_id

        files = []
        for d in [raw_dir, runtime_dir]:
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
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
        candidates = [
            project_dir / "raw_load_data" / node_id / file_name,
            project_dir / "assets" / "runtime" / node_id / file_name,
        ]
        for p in candidates:
            if p.exists():
                return p
        return None
