# Runtime 数据处理一体化 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将资产绑定页面 Step ③ 从"上传预处理好的 runtime CSV"改为"上传原始负荷 Excel + 一键批量处理"，集成 scripts/ 下的建模脚本。

**Architecture:** 后端新增 `LoadDataProcessingService` 调用脚本处理函数，通过 SSE 推送日志到前端。处理完成后调用 `register_asset_file()` 注册产物到 `project.assets`，复用现有侧边栏对勾逻辑。前端 Step ③ 改为三区布局（上传 + 日志 + 预览）。

**Tech Stack:** FastAPI SSE (sse-starlette), React 19 + TypeScript, Python scikit-learn + matplotlib + pandas

---

## 文件结构

```
Create:
  scripts/__init__.py
  backend/services/load_data_processing_service.py
  backend/models/load_data_models.py

Modify:
  scripts/全年逐日典型日聚类1h级居民负荷建模.py     → 提取 process_raw_data() 接口
  scripts/按工休和年用电峰谷分析的1h级工商业负荷建模_改.py → 同上
  scripts/build_runtime_files_residential.py       → 提取 process_one_node() 接口
  scripts/build_runtime_files_industrial_or_commercial.py → 同上
  backend/services/project_model_service.py         → 新增 register_asset_file()
  backend/routes/assets.py                          → 新增3个端点
  backend/models/project_model.py                   → 新增响应模型
  frontend/src/pages/workspace/AssetsPage.tsx        → Step ③ 重写
  frontend/src/services/assets.ts                    → 新增 API 调用函数
  pyproject.toml                                    → 加 scikit-learn + scripts*
  start.bat                                         → 加 scikit-learn
```

---

### Task 1: 添加 `scripts/__init__.py` 并使包可导入

**Files:**
- Create: `scripts/__init__.py`
- Modify: `pyproject.toml:53-54`

- [ ] **Step 1: 创建空的 `scripts/__init__.py`**

```bash
touch scripts/__init__.py
```

- [ ] **Step 2: 修改 `pyproject.toml` 使 scripts 可被 backend import**

将：
```
include = ["storage_engine_project*", "backend*"]
```
改为：
```
include = ["storage_engine_project*", "backend*", "scripts*"]
```

- [ ] **Step 3: 添加 scikit-learn 依赖到 pyproject.toml**

在 `[dependencies]` 列表末尾新增：
```
"scikit-learn>=1.7,<2.0",
```

同时在 `[full]` 列表末尾也新增：
```
"scikit-learn>=1.7,<2.0",
```

- [ ] **Step 4: 验证导入**

```bash
cd d:/storage_web_platform_3 && python -c "import scripts; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py pyproject.toml
git commit -m "feat: 添加 scripts 包和 scikit-learn 依赖"
```

---

### Task 2: 新增 `register_asset_file()` 方法

**Files:**
- Modify: `backend/services/project_model_service.py:245`

- [ ] **Step 1: 在 `ProjectModelService` 类中添加 `register_asset_file()` 方法**

在 `get_asset()` 方法之后插入：

```python
def register_asset_file(
    self,
    project_id: str,
    file_path: Path,
    category: str,
    subfolder: str | None = None,
    metadata: dict | None = None,
) -> tuple[AssetRef, ProjectModel, Path]:
    """注册已有文件到 project.assets（无需 UploadFile 对象）"""
    project = self.load_project(project_id)
    asset_id = self.generate_asset_id()
    safe_name = file_path.name
    asset_dir = self._assets_dir(project_id) / category
    if subfolder:
        asset_dir = asset_dir / subfolder
    asset_dir.mkdir(parents=True, exist_ok=True)

    target_file = asset_dir / f"{asset_id}_{safe_name}"
    shutil.copy2(str(file_path), str(target_file))

    asset = AssetRef(
        file_id=asset_id,
        file_name=safe_name,
        source_type="generated",
        metadata={
            "category": category,
            "subfolder": subfolder,
            "stored_path": str(target_file.resolve()),
            **(metadata or {}),
        },
    )
    project.assets[asset_id] = asset
    self._mark_current_asset(
        project, category, asset_id,
        subfolder=subfolder,
        runtime_kind=metadata.get("runtime_kind") if metadata else None,
    )
    _, project_file = self.save_project(project)
    return asset, project, project_file
```

需要从 shutil 导入 copy2（检查文件顶部已有 `import shutil`）。

- [ ] **Step 2: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('backend/services/project_model_service.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/project_model_service.py
git commit -m "feat: 新增 register_asset_file 方法支持磁盘文件注册"
```

---

### Task 3: 脚本接口化——居民建模脚本

**Files:**
- Modify: `scripts/全年逐日典型日聚类1h级居民负荷建模.py`

- [ ] **Step 1: 添加可被调用的入口函数**

在文件末尾 `main()` 之后新增：

```python
def process_raw_data(raw_excel_path: str | Path, output_dir: str | Path) -> dict:
    """
    供后端调用的入口：处理单个原始负荷 Excel，输出全部建模产物。

    Args:
        raw_excel_path: 用户上传的原始 Excel 路径（两列：时间+负荷）
        output_dir: 输出目录（如 raw_load_data/load_01/）

    Returns:
        {"charts": ["01_居民典型日曲线.png", ...], "excel_files": [...], "error": None}
    """
    file_path = Path(raw_excel_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    process_one_company(file_path, output_root)

    charts = sorted(
        [p.name for p in output_root.glob("*.png")],
        key=lambda x: x
    )
    excel_files = sorted(
        [p.name for p in output_root.glob("*.xlsx")],
        key=lambda x: x
    )

    return {"charts": charts, "excel_files": excel_files, "error": None}
```

- [ ] **Step 2: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('scripts/全年逐日典型日聚类1h级居民负荷建模.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add "scripts/全年逐日典型日聚类1h级居民负荷建模.py"
git commit -m "refactor: 居民建模脚本添加 process_raw_data 入口"
```

---

### Task 4: 脚本接口化——工商业建模脚本

**Files:**
- Modify: `scripts/按工休和年用电峰谷分析的1h级工商业负荷建模_改.py`

- [ ] **Step 1: 添加可被调用的入口函数**

在文件末尾 `main()` 之后新增：

```python
def process_raw_data(raw_excel_path: str | Path, output_dir: str | Path) -> dict:
    """
    供后端调用的入口：处理单个原始工商业负荷 Excel。
    """
    file_path = Path(raw_excel_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    process_one_company(file_path, output_root)

    charts = sorted([p.name for p in output_root.glob("*.png")], key=lambda x: x)
    excel_files = sorted([p.name for p in output_root.glob("*.xlsx")], key=lambda x: x)

    return {"charts": charts, "excel_files": excel_files, "error": None}
```

- [ ] **Step 2: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('scripts/按工休和年用电峰谷分析的1h级工商业负荷建模_改.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add "scripts/按工休和年用电峰谷分析的1h级工商业负荷建模_改.py"
git commit -m "refactor: 工商业建模脚本添加 process_raw_data 入口"
```

---

### Task 5: 脚本接口化——build_runtime 脚本（居民 + 工商业）

**Files:**
- Modify: `scripts/build_runtime_files_residential.py`
- Modify: `scripts/build_runtime_files_industrial_or_commercial.py`

- [ ] **Step 1: 居民 build 脚本添加入口**

在 `scripts/build_runtime_files_residential.py` 末尾 `main()` 之后新增：

```python
def process_one_node(input_dir: str | Path, output_dir: str | Path) -> dict:
    """
    供后端调用：从中间 Excel 生成 runtime CSV。

    Args:
        input_dir: 包含 01_全年逐日模型映射表.xlsx / 02_居民典型日模型库.xlsx 的目录
        output_dir: runtime CSV 输出目录

    Returns:
        {"year_map_path": str, "model_library_path": str}
    """
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from pathlib import Path as P

    year_map_df = load_year_model_map(in_dir / MAP_XLSX_NAME)
    library_df = load_model_library(in_dir / LIB_XLSX_NAME)
    internal_map = build_internal_model_mapping(year_map_df, library_df)

    runtime_year_map_df = build_runtime_year_model_map(year_map_df, internal_map)
    runtime_library_df = build_runtime_model_library(library_df, internal_map)

    map_path = out_dir / OUT_MAP_CSV_NAME
    lib_path = out_dir / OUT_LIB_CSV_NAME

    runtime_year_map_df.to_csv(map_path, index=False, encoding="utf-8-sig")
    runtime_library_df.to_csv(lib_path, index=False, encoding="utf-8-sig")

    return {"year_map_path": str(map_path), "model_library_path": str(lib_path)}
```

- [ ] **Step 2: 工商业 build 脚本添加入口**

在 `scripts/build_runtime_files_industrial_or_commercial.py` 末尾 `main()` 之后新增：

```python
def process_one_node(input_dir: str | Path, output_dir: str | Path) -> dict:
    """
    供后端调用：从中间 Excel 生成 runtime CSV。

    Args:
        input_dir: 包含 03_全年逐日模型映射表.xlsx / 04_组合典型日负荷模型库.xlsx 的目录
        output_dir: runtime CSV 输出目录
    """
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    year_map_df = load_year_model_map(in_dir / MAP_XLSX_NAME)
    library_df = load_model_library(in_dir / LIB_XLSX_NAME)
    internal_map = build_internal_model_mapping(year_map_df, library_df)

    runtime_year_map_df = build_runtime_year_model_map(year_map_df, internal_map)
    runtime_library_df = build_runtime_model_library(library_df, internal_map)

    map_path = out_dir / OUT_MAP_CSV_NAME
    lib_path = out_dir / OUT_LIB_CSV_NAME

    runtime_year_map_df.to_csv(map_path, index=False, encoding="utf-8-sig")
    runtime_library_df.to_csv(lib_path, index=False, encoding="utf-8-sig")

    return {"year_map_path": str(map_path), "model_library_path": str(lib_path)}
```

- [ ] **Step 3: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('scripts/build_runtime_files_residential.py', encoding='utf-8').read()); print('OK')" && python -c "import ast; ast.parse(open('scripts/build_runtime_files_industrial_or_commercial.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/build_runtime_files_residential.py scripts/build_runtime_files_industrial_or_commercial.py
git commit -m "refactor: build_runtime 脚本添加 process_one_node 入口"
```

---

### Task 6: 新增 API 模型

**Files:**
- Create: `backend/models/load_data_models.py`

- [ ] **Step 1: 创建模型文件**

```python
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RawLoadDataUploadResponse(BaseModel):
    success: bool
    node_id: str
    file_name: str
    stored_path: str


class ProcessRuntimeRequest(BaseModel):
    node_ids: List[str] = Field(..., min_length=1)


class PreviewFileInfo(BaseModel):
    name: str
    type: str  # "image" | "csv" | "text"
    url: str


class PreviewNodeResponse(BaseModel):
    node_id: str
    files: List[PreviewFileInfo]
```

- [ ] **Step 2: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('backend/models/load_data_models.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/models/load_data_models.py
git commit -m "feat: 新增原始数据处理 API 模型"
```

---

### Task 7: 新增 `LoadDataProcessingService`

**Files:**
- Create: `backend/services/load_data_processing_service.py`

- [ ] **Step 1: 创建处理服务**

```python
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
```

- [ ] **Step 2: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('backend/services/load_data_processing_service.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/load_data_processing_service.py
git commit -m "feat: 新增 LoadDataProcessingService 批量处理服务"
```

---

### Task 8: 新增 API 端点

**Files:**
- Modify: `backend/routes/assets.py`

- [ ] **Step 1: 添加三个新端点**

在 `backend/routes/assets.py` 文件末尾 `delete_device_record` 函数之后添加：

```python
import csv
import io
import json as json_mod

from fastapi.responses import StreamingResponse, Response
from models.load_data_models import (
    RawLoadDataUploadResponse,
    ProcessRuntimeRequest,
    PreviewFileInfo,
    PreviewNodeResponse,
)
from services.load_data_processing_service import LoadDataProcessingService

processing_service = LoadDataProcessingService(project_service=project_service)


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
        service = LoadDataProcessingService(project_service=project_service)
        files = service.list_preview_files(project_id, node_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    preview_files = [
        PreviewFileInfo(
            name=f["name"],
            type=f["type"],
            url=f"/api/assets/preview/{project_id}/{node_id}/{f['name']}",
        )
        for f in files
    ]
    return PreviewNodeResponse(node_id=node_id, files=preview_files)


@router.get("/preview/{project_id}/{node_id}/{file_name:path}")
def preview_file_content(project_id: str, node_id: str, file_name: str):
    """返回预览文件内容：图片 binary，CSV JSON 数组"""
    service = LoadDataProcessingService(project_service=project_service)
    file_path = service.get_preview_file_path(project_id, node_id, file_name)
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"文件不存在：{file_name}")

    suffix = file_path.suffix.lower()
    if suffix == ".png":
        return Response(content=file_path.read_bytes(), media_type="image/png")
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
```

同时需要修改文件顶部的 import，新增：
```python
import csv
import io

from fastapi.responses import StreamingResponse, Response
from models.load_data_models import (
    RawLoadDataUploadResponse,
    ProcessRuntimeRequest,
    PreviewFileInfo,
    PreviewNodeResponse,
)
from services.load_data_processing_service import LoadDataProcessingService
```

在现有 router 定义之后立即初始化：
```python
processing_service = LoadDataProcessingService(project_service=project_service)
```

确保 `ProcessRuntimeRequest` 包含 `project_id` 字段；需要在 `load_data_models.py` 中加上：
```python
class ProcessRuntimeRequest(BaseModel):
    project_id: str
    node_ids: List[str] = Field(..., min_length=1)
```

- [ ] **Step 2: 更新 load_data_models.py 的 ProcessRuntimeRequest 加 project_id**

在 `ProcessRuntimeRequest` 的定义中添加 `project_id` 字段（回 Task 6 修改）：

```python
class ProcessRuntimeRequest(BaseModel):
    project_id: str
    node_ids: List[str] = Field(..., min_length=1)
```

- [ ] **Step 3: 语法检查**

```bash
cd d:/storage_web_platform_3 && python -c "import ast; ast.parse(open('backend/routes/assets.py').read()); print('OK')" && python -c "import ast; ast.parse(open('backend/models/load_data_models.py').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/routes/assets.py backend/models/load_data_models.py
git commit -m "feat: 新增原始数据上传、SSE 批处理和文件预览 API 端点"
```

---

### Task 9: 更新 `start.bat` 依赖

**Files:**
- Modify: `start.bat`

- [ ] **Step 1: 修改 fallback 安装命令（第 113 行）**

将：
```batch
"!PYTHON_EXE!" -m pip install fastapi uvicorn "pydantic>=2" python-multipart numpy scipy pandas openpyxl pywin32 joblib --quiet 2>&1
```
改为：
```batch
"!PYTHON_EXE!" -m pip install fastapi uvicorn "pydantic>=2" python-multipart numpy scipy pandas openpyxl pywin32 joblib scikit-learn --quiet 2>&1
```

- [ ] **Step 2: 修改预检命令（第 143 行）**

将：
```batch
"!PYTHON_EXE!" -c "import fastapi, uvicorn, numpy, pandas; print('  Core modules OK')" 2>&1
```
改为：
```batch
"!PYTHON_EXE!" -c "import fastapi, uvicorn, numpy, pandas, sklearn; print('  Core modules OK')" 2>&1
```

- [ ] **Step 3: Commit**

```bash
git add start.bat
git commit -m "chore: start.bat 添加 scikit-learn 依赖"
```

---

### Task 10: 前端——新增 API 调用函数

**Files:**
- Modify: `frontend/src/services/assets.ts`

- [ ] **Step 1: 添加三个新 API 函数**

在 `assets.ts` 末尾添加：

```typescript
import { http } from './http';

const BASE = '/api/assets';

export async function uploadRawLoadData(
  projectId: string,
  nodeId: string,
  file: File,
): Promise<{ success: boolean; node_id: string; file_name: string; stored_path: string }> {
  const form = new FormData();
  form.append('project_id', projectId);
  form.append('node_id', nodeId);
  form.append('file', file);
  const res = await fetch(`${BASE}/raw-load-data/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listUploadedNodes(
  projectId: string,
): Promise<{ uploaded_nodes: string[]; processed_nodes: string[] }> {
  const res = await fetch(`${BASE}/raw-load-data/uploaded/${projectId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function processRuntime(
  projectId: string,
  nodeIds: string[],
  onEvent: (event: Record<string, unknown>) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();
  const body = JSON.stringify({ project_id: projectId, node_ids: nodeIds });

  fetch(`${BASE}/process-runtime`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    signal: controller.signal,
  }).then(async (res) => {
    if (!res.ok) { onError(new Error(await res.text())); return; }
    const reader = res.body?.getReader();
    if (!reader) { onDone(); return; }
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { onEvent(JSON.parse(line.slice(6))); } catch {}
        }
      }
    }
    onDone();
  }).catch((err) => {
    if (err.name !== 'AbortError') onError(err);
  });

  return controller;
}

export async function listPreviewFiles(
  projectId: string,
  nodeId: string,
): Promise<{ node_id: string; files: Array<{ name: string; type: string; url: string }> }> {
  const res = await fetch(`${BASE}/preview/${projectId}/${nodeId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchPreviewContent(
  projectId: string,
  nodeId: string,
  fileName: string,
): Promise<{ file_name?: string; columns?: string[]; rows?: Array<Record<string, string>>; content?: string } | Blob> {
  const url = `${BASE}/preview/${projectId}/${nodeId}/${fileName}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('image')) return res.blob();
  return res.json();
}
```

- [ ] **Step 2: TypeScript 类型检查**

```bash
cd d:/storage_web_platform_3/frontend && npx tsc -b --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/assets.ts
git commit -m "feat: 前端新增 raw-load-data、SSE 批处理和预览 API 函数"
```

---

### Task 11: 前端——重写 AssetsPage Step ③

**Files:**
- Modify: `frontend/src/pages/workspace/AssetsPage.tsx`

- [ ] **Step 1: 新增状态变量**

在现有 `useState` 区域添加：

```typescript
// Step 3 - 原始数据上传
const [rawNodeId, setRawNodeId] = useState('');
const [rawFile, setRawFile] = useState<File | null>(null);
const [rawUploading, setRawUploading] = useState(false);
const [uploadedNodeIds, setUploadedNodeIds] = useState<string[]>([]);
const [processedNodeIds, setProcessedNodeIds] = useState<string[]>([]);

// Step 3 - 处理日志
const [processing, setProcessing] = useState(false);
const [logLines, setLogLines] = useState<Array<{ id: number; node: string; message: string; type: 'progress' | 'done' | 'error' }>>([]);
const [processProgress, setProcessProgress] = useState({ current: 0, total: 0 });
const [processAbort, setProcessAbort] = useState<AbortController | null>(null);

// Step 3 - 文件预览
const [previewNodeId, setPreviewNodeId] = useState('');
const [previewFile, setPreviewFile] = useState<{ name: string; type: string } | null>(null);
const [previewFiles, setPreviewFiles] = useState<Array<{ name: string; type: string; url: string }>>([]);
const [previewLoading, setPreviewLoading] = useState(false);
const [previewContent, setPreviewContent] = useState<{
  kind: 'image' | 'csv' | 'text';
  imageUrl?: string;
  columns?: string[];
  rows?: Array<Record<string, string>>;
  textContent?: string;
} | null>(null);
const logIdRef = useRef(0);
```

- [ ] **Step 2: 新增辅助函数**

```typescript
async function refreshUploadedNodes() {
  if (!projectId) return;
  try {
    const data = await listUploadedNodes(projectId);
    setUploadedNodeIds(data.uploaded_nodes);
    setProcessedNodeIds(data.processed_nodes);
  } catch {}
}

async function onUploadRawData() {
  if (!projectId || !rawNodeId || !rawFile) return;
  setRawUploading(true);
  setError(null);
  try {
    await uploadRawLoadData(projectId, rawNodeId, rawFile);
    setRawFile(null);
    await refreshUploadedNodes();
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    setRawUploading(false);
  }
}

function onStartProcessing() {
  if (!projectId || processing) return;
  const nodeIds = uploadedNodeIds.filter((id) => !processedNodeIds.includes(id));
  if (nodeIds.length === 0) return;
  setProcessing(true);
  setLogLines([]);
  setProcessProgress({ current: 0, total: nodeIds.length });

  const ctrl = processRuntime(
    projectId,
    nodeIds,
    (event) => {
      const line = {
        id: ++logIdRef.current,
        node: String(event.node || ''),
        message: String(event.message || ''),
        type: (event.type as 'progress' | 'done' | 'error') || 'progress',
      };
      setLogLines((prev) => [...prev.slice(-49), line]);
      if (event.type === 'done' || event.type === 'error') {
        setProcessProgress((p) => ({ ...p, current: (event.current as number) || p.current }));
      }
    },
    async () => {
      setProcessing(false);
      setProcessAbort(null);
      await refreshUploadedNodes();
      await loadDashboard();
    },
    (err) => {
      setError(err.message);
      setProcessing(false);
      setProcessAbort(null);
    },
  );
  setProcessAbort(ctrl);
}

async function onSelectPreviewNode(nodeId: string) {
  setPreviewNodeId(nodeId);
  setPreviewFile(null);
  setPreviewContent(null);
  if (!nodeId || !projectId) return;
  setPreviewLoading(true);
  try {
    const data = await listPreviewFiles(projectId, nodeId);
    setPreviewFiles(data.files);
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    setPreviewLoading(false);
  }
}

async function onSelectPreviewFile(file: { name: string; type: string }) {
  setPreviewFile(file);
  if (!projectId || !previewNodeId) return;
  setPreviewLoading(true);
  try {
    const result = await fetchPreviewContent(projectId, previewNodeId, file.name);
    if (result instanceof Blob) {
      setPreviewContent({ kind: 'image', imageUrl: URL.createObjectURL(result) });
    } else if ('content' in result && result.content) {
      setPreviewContent({ kind: 'text', textContent: result.content });
    } else if ('rows' in result && result.rows) {
      setPreviewContent({
        kind: 'csv',
        columns: result.columns,
        rows: result.rows,
      });
    }
  } catch (err) {
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    setPreviewLoading(false);
  }
}
```

- [ ] **Step 3: 替换 Step ③ JSX**

将现有的 `{/* Step 3: Runtime Files */}` 整块替换为新的三区布局：

```tsx
{/* Step 3: Runtime Files */}
<section className="mb-5 rounded-2xl border border-border bg-card p-5">
  <div className="flex items-center justify-between gap-3 flex-wrap">
    <StepBadge step={3} label="Runtime 文件绑定" />
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        uploadedCount > 0
          ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
          : 'border border-amber-500/30 bg-amber-500/10 text-amber-600'
      }`}
    >
      已上传 {uploadedNodeIds.length}/{totalLoadNodes} · 已处理 {processedNodeIds.length}/{totalLoadNodes}
    </span>
  </div>

  {/* ── ① 上传原始数据 ── */}
  <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
    <div className="mb-2 text-sm font-semibold text-foreground">① 上传原始数据</div>
    <div className="flex items-center gap-3 flex-wrap">
      <select
        value={rawNodeId}
        onChange={(e) => setRawNodeId(e.target.value)}
        className="rounded-xl border border-border bg-card px-3 py-2 text-sm"
      >
        <option value="">选择负荷节点</option>
        {loadNodes
          .filter((n) => !uploadedNodeIds.includes(n.id))
          .map((n) => (
            <option key={n.id} value={n.id}>{n.label}</option>
          ))}
      </select>
      <label className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 h-7 px-3 text-sm font-medium cursor-pointer hover:bg-muted transition-colors">
        <span className="text-base">📁</span> 选择文件
        <input
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          onChange={(e) => setRawFile(e.target.files?.[0] ?? null)}
        />
      </label>
      {rawFile && <span className="text-xs text-muted-foreground truncate max-w-[160px]">{rawFile.name}</span>}
      <Button size="sm" onClick={onUploadRawData} disabled={!rawNodeId || !rawFile || rawUploading}>
        上传
      </Button>
    </div>
    {uploadedNodeIds.length > 0 && (
      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <span className="text-xs text-muted-foreground">
          已上传：{uploadedNodeIds.map((id) => (
            <span key={id} className="mr-1.5 mb-0.5 inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">{id} ✓</span>
          ))}
        </span>
        <Button size="sm" onClick={onStartProcessing} disabled={processing || uploadedNodeIds.length === 0}>
          {processing ? '处理中...' : '一键处理 →'}
        </Button>
        {processing && processAbort && (
          <Button size="sm" variant="outline" onClick={() => { processAbort.abort(); setProcessing(false); }}>
            取消
          </Button>
        )}
      </div>
    )}
    {uploadedNodeIds.length > 0 && (
      <div className="mt-3 text-xs text-muted-foreground">
        待处理：{uploadedNodeIds.filter((id) => !processedNodeIds.includes(id)).join(', ') || '无'}
      </div>
    )}
  </div>

  {/* ── ② 处理日志 ── */}
  {logLines.length > 0 && (
    <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
      <div className="mb-2 text-sm font-semibold text-foreground">② 处理日志</div>
      {processProgress.total > 0 && (
        <div className="mb-3 h-2 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${Math.round((processProgress.current / processProgress.total) * 100)}%` }}
          />
        </div>
      )}
      <div className="max-h-48 overflow-y-auto space-y-0.5 text-xs font-mono">
        {logLines.map((line) => (
          <div
            key={line.id}
            className={
              line.type === 'error' ? 'text-red-600' :
              line.type === 'done' ? 'text-emerald-600' :
              'text-muted-foreground'
            }
          >
            [{line.type === 'error' ? '✗' : line.type === 'done' ? '✓' : '·'}] {line.node}: {line.message}
          </div>
        ))}
      </div>
    </div>
  )}

  {/* ── ③ 文件预览 ── */}
  <div className="mt-4 rounded-xl border border-border bg-muted/20 p-4">
    <div className="mb-2 text-sm font-semibold text-foreground">③ 文件预览</div>
    <div className="flex items-center gap-3 flex-wrap mb-3">
      <select
        value={previewNodeId}
        onChange={(e) => onSelectPreviewNode(e.target.value)}
        className="rounded-xl border border-border bg-card px-3 py-2 text-sm"
      >
        <option value="">选择节点</option>
        {processedNodeIds.map((id) => (
          <option key={id} value={id}>{id}</option>
        ))}
      </select>
      <select
        value={previewFile?.name || ''}
        onChange={(e) => {
          const f = previewFiles.find((pf) => pf.name === e.target.value);
          if (f) onSelectPreviewFile(f);
        }}
        className="rounded-xl border border-border bg-card px-3 py-2 text-sm"
        disabled={!previewNodeId || previewFiles.length === 0}
      >
        <option value="">选择文件</option>
        {previewFiles.map((f) => (
          <option key={f.name} value={f.name}>{f.name} ({f.type})</option>
        ))}
      </select>
    </div>
    {previewLoading ? (
      <div className="text-xs text-muted-foreground">加载中...</div>
    ) : previewContent ? (
      previewContent.kind === 'image' ? (
        <img src={previewContent.imageUrl} alt="预览" className="max-w-full max-h-96 rounded-xl border" />
      ) : previewContent.kind === 'csv' ? (
        <div className="max-h-80 overflow-auto rounded-xl border">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 sticky top-0">
              <tr>
                {previewContent.columns?.map((col) => (
                  <th key={col} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {previewContent.rows?.slice(0, 100).map((row, i) => (
                <tr key={i} className="border-t border-border/50">
                  {previewContent.columns?.map((col) => (
                    <td key={col} className="px-2 py-1 whitespace-nowrap">{row[col]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {previewContent.rows && previewContent.rows.length > 100 && (
            <div className="px-2 py-1 text-xs text-muted-foreground">
              显示前 100 行，共 {previewContent.rows.length} 行
            </div>
          )}
        </div>
      ) : (
        <pre className="max-h-80 overflow-auto rounded-xl border bg-muted/30 p-3 text-xs">{previewContent.textContent}</pre>
      )
    ) : (
      <div className="text-xs text-muted-foreground">选择已处理的节点和文件后预览</div>
    )}
  </div>

  <p className="mt-4 text-xs text-muted-foreground">
    上传原始负荷 Excel（两列：时间 + 负荷），脚本将自动根据节点类型（居民/工业/商业）选择建模算法生成 runtime 文件。
  </p>
</section>
```

- [ ] **Step 4: 添加 useEffect 在页面加载时刷新节点状态**

在组件中添加：

```typescript
useEffect(() => {
  if (projectId) refreshUploadedNodes();
}, [projectId, loadNodes]);
```

- [ ] **Step 5: 清理旧的 Step 3 相关代码**

删除以下不再使用的状态和函数：
- `runtimeNodeId`, `setRuntimeNodeId`
- `yearMapFile`, `setYearMapFile`, `modelLibraryFile`, `setModelLibraryFile`
- `selectedRuntimeNode`, `selectedRuntimeBound`, `selectedRuntimeUploaded`
- `onUploadRuntime()` 函数

- [ ] **Step 6: 添加新 imports**

在文件顶部修改现有 `useState` 导入为 `useRef, useState`，并添加新导入：
```typescript
import { useEffect, useRef, useState } from 'react';
import {
  listProjectAssets,
  uploadTariffFile,
  uploadDeviceLibraryFile,
  uploadRuntimeFile,
  uploadRawLoadData,
  listUploadedNodes,
  processRuntime,
  listPreviewFiles,
  fetchPreviewContent,
} from '../../services/assets';
```

- [ ] **Step 7: TypeScript 类型检查 + 构建**

```bash
cd d:/storage_web_platform_3/frontend && npx tsc -b --noEmit && pnpm build
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/workspace/AssetsPage.tsx
git commit -m "feat: 重写 AssetsPage Step ③ 为原始数据上传 + 一键处理 + 预览"
```

---

### Task 12: 集成验证

- [ ] **Step 1: 全部 TypeScript 类型检查**

```bash
cd d:/storage_web_platform_3/frontend && npx tsc -b --noEmit
```

- [ ] **Step 2: 全部 Python 语法检查**

```bash
cd d:/storage_web_platform_3 && for f in backend/services/load_data_processing_service.py backend/services/project_model_service.py backend/models/load_data_models.py backend/routes/assets.py; do python -c "import ast; ast.parse(open('$f').read()); print(f'$f OK')"; done
```

- [ ] **Step 3: 前端构建**

```bash
cd d:/storage_web_platform_3/frontend && pnpm build
```

- [ ] **Step 4: 同步到交付工程并重启 uvicorn 手动测试**

```bash
cp -r backend/static/* D:/cess-delivery/backend/static/
cp backend/services/load_data_processing_service.py D:/cess-delivery/backend/services/
cp backend/services/project_model_service.py D:/cess-delivery/backend/services/
cp backend/models/load_data_models.py D:/cess-delivery/backend/models/
cp backend/routes/assets.py D:/cess-delivery/backend/routes/
cp backend/storage_fastapi_backend.py D:/cess-delivery/backend/
cp -r scripts/ D:/cess-delivery/scripts/
cp start.bat D:/cess-delivery/
cp pyproject.toml D:/cess-delivery/
```

- [ ] **Step 5: Commit final**

```bash
git add -A && git commit -m "feat: 完成 runtime 数据处理一体化功能集成"
```
