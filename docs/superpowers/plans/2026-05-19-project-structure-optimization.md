# 工程项目目录结构优化 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 理清文件边界——分离原始数据与建模产物，展平输出层级，处理后自动清理中间文件，消除空目录残留。

**Architecture:** 3 个文件改动：`load_data_processing_service.py`（核心路径逻辑）、两个建模脚本的 `process_raw_data()`（展平输出）。新增 `modeling_output/{node_id}/` 目录存放建模产物 PNG。不改 build/、solver_runs/、前端。

**Tech Stack:** Python 3.11, pathlib, shutil

---

### Task 1: 展平 `load_modeling_residential.py` 的 `process_raw_data()` 输出

**Files:**
- Modify: `backend/services/load_modeling_residential.py:606-619`

- [ ] **Step 1: 添加 `import shutil`**

在文件头部 `import warnings` 下方插入：
```python
import shutil
```

- [ ] **Step 2: 在 `process_raw_data()` 函数内添加展平逻辑**

将 `process_raw_data()` 改为：
```python
def process_raw_data(raw_excel_path: str | Path, output_dir: str | Path) -> dict:
    file_path = Path(raw_excel_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    process_one_company(file_path, output_root)

    # process_one_company 会创建 output_root / file_path.stem / 子目录，
    # 把所有文件搬到 output_root / 下，消除多余层级
    nested_dir = output_root / file_path.stem
    if nested_dir.is_dir():
        for f in nested_dir.iterdir():
            shutil.move(str(f), str(output_root / f.name))
        nested_dir.rmdir()

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

- [ ] **Step 3: 语法检查**

```bash
python -m py_compile backend/services/load_modeling_residential.py
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/load_modeling_residential.py
git commit -m "feat: flatten modeling output in residential load modeling script"
```

---

### Task 2: 展平 `load_modeling_industrial.py` 的 `process_raw_data()` 输出

**Files:**
- Modify: `backend/services/load_modeling_industrial.py:759-766`

- [ ] **Step 1: 添加 `import shutil`**

在文件头部 `import warnings` 下方插入：
```python
import shutil
```

- [ ] **Step 2: 在 `process_raw_data()` 函数内添加展平逻辑**

将 `process_raw_data()` 改为：
```python
def process_raw_data(raw_excel_path: str | Path, output_dir: str | Path) -> dict:
    file_path = Path(raw_excel_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    process_one_company(file_path, output_root)

    # process_one_company 会创建 output_root / file_path.stem / 子目录，
    # 把所有文件搬到 output_root / 下，消除多余层级
    nested_dir = output_root / file_path.stem
    if nested_dir.is_dir():
        for f in nested_dir.iterdir():
            shutil.move(str(f), str(output_root / f.name))
        nested_dir.rmdir()

    charts = sorted([p.name for p in output_root.glob("*.png")], key=lambda x: x)
    excel_files = sorted([p.name for p in output_root.glob("*.xlsx")], key=lambda x: x)
    return {"charts": charts, "excel_files": excel_files, "error": None}
```

- [ ] **Step 3: 语法检查**

```bash
python -m py_compile backend/services/load_modeling_industrial.py
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/load_modeling_industrial.py
git commit -m "feat: flatten modeling output in industrial/commercial load modeling script"
```

---

### Task 3: 修改 `process_all_nodes()` —— 引入 `modeling_output/` + 自动清理

**Files:**
- Modify: `backend/services/load_data_processing_service.py:50-155`

- [ ] **Step 1: 修改 process_all_nodes() 路径逻辑**

将 `process_all_nodes()` 方法中的路径构建和处理逻辑改为：

```python
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
            model_dir = project_dir / "modeling_output" / node_id
            runtime_dir = project_dir / "assets" / "runtime" / node_id
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

                # 1. 建模（输出到 modeling_output/{node_id}/，展平后文件直接在此目录）
                if cat == "residential":
                    from services.load_modeling_residential import process_raw_data as model_residential
                    result = model_residential(raw_file, str(model_dir))
                else:
                    from services.load_modeling_industrial import process_raw_data as model_industrial
                    result = model_industrial(raw_file, str(model_dir))

                yield f"data: {json.dumps({'type': 'progress', 'node': node_id, 'step': 'convert', 'message': '建模完成，开始生成 runtime CSV...', 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 2. 转换（从 modeling_output/{node_id}/ 读取中间 Excel）
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

                # 5. 清理 modeling_output/{node_id}/ 下的中间文件，只保留 PNG
                for f in model_dir.glob("*.xlsx"):
                    f.unlink()
                for f in model_dir.glob("*.txt"):
                    f.unlink()

                success += 1
                charts = result.get("charts", [])
                yield f"data: {json.dumps({'type': 'done', 'node': node_id, 'charts': charts, 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"

            except Exception as exc:
                failed += 1
                tb = traceback.format_exc()
                yield f"data: {json.dumps({'type': 'error', 'node': node_id, 'message': str(exc), 'traceback': tb, 'current': idx + 1, 'total': len(node_ids)}, ensure_ascii=False)}\n\n"

            await asyncio.sleep(0)

        yield f"data: {json.dumps({'type': 'complete', 'total': len(node_ids), 'success': success, 'failed': failed}, ensure_ascii=False)}\n\n"
```

- [ ] **Step 2: 语法检查**

```bash
python -m py_compile backend/services/load_data_processing_service.py
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/load_data_processing_service.py
git commit -m "feat: route modeling output to modeling_output/ with auto-cleanup of intermediates"
```

---

### Task 4: 更新 `list_preview_files()` 和 `get_preview_file_path()` 扫描 `modeling_output/`

**Files:**
- Modify: `backend/services/load_data_processing_service.py:167-200`

- [ ] **Step 1: 更新 `list_preview_files()`**

将 `raw_dir` 引用改为 `model_dir`：
```python
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
```

- [ ] **Step 2: 更新 `get_preview_file_path()`**

将 `raw_base` 替换为 `model_base`：
```python
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
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/load_data_processing_service.py
git commit -m "fix: preview methods now scan modeling_output/ instead of raw_load_data/"
```

---

### Task 5: 更新 `delete_raw_load_data()` 联动删除 `modeling_output/`

**Files:**
- Modify: `backend/services/load_data_processing_service.py:156-165`

- [ ] **Step 1: 添加 modeling_output 删除**

将 `delete_raw_load_data()` 改为：
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/load_data_processing_service.py
git commit -m "fix: delete_raw_load_data also removes modeling_output/{node_id}"
```

---

### Task 6: 修复 `get_uploaded_nodes()` —— 检查文件而非仅目录

**Files:**
- Modify: `backend/services/load_data_processing_service.py:28-36`

- [ ] **Step 1: 改为检查目录内是否有 xlsx 文件**

将 `get_uploaded_nodes()` 改为：
```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/load_data_processing_service.py
git commit -m "fix: get_uploaded_nodes checks for actual xlsx files, not just dirs"
```

---

### Task 7: 添加一次性清理方法

**Files:**
- Modify: `backend/services/load_data_processing_service.py`（末尾）

- [ ] **Step 1: 添加 `cleanup_empty_dirs()` 静态方法**

在类末尾（`get_preview_file_path` 之后）添加：
```python
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

        # 4) build/solver_workspace/inputs/tariff/ —— 空
        for sub in ["tariff", "storage"]:
            d = project_dir / "build" / "solver_workspace" / "inputs" / sub
            if _rm_if_empty(d):
                removed.append(str(d.relative_to(project_dir)))

        # 5) build/solver_workspace/outputs/ —— 空
        out_d = project_dir / "build" / "solver_workspace" / "outputs"
        if _rm_tree_if_empty(out_d):
            removed.append(str(out_d.relative_to(project_dir)))

        return {"project_id": project_id, "removed": removed}
```

- [ ] **Step 2: 语法检查**

```bash
python -m py_compile backend/services/load_data_processing_service.py
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/load_data_processing_service.py
git commit -m "feat: add cleanup_empty_dirs() for legacy project directory cleanup"
```

---

### Task 8: 构建 + 同步交付工程 + 验证

**Files:**
- Build: frontend（无需重新构建，无前端改动）
- Sync: 3 个后端文件到 `D:\cess-delivery`

- [ ] **Step 1: 后端语法全量检查**

```bash
cd backend
python -m py_compile services/load_data_processing_service.py
python -m py_compile services/load_modeling_residential.py
python -m py_compile services/load_modeling_industrial.py
```

预期：全部 PASS（无输出）

- [ ] **Step 2: 同步到交付工程**

```bash
cp backend/services/load_data_processing_service.py D:/cess-delivery/backend/services/load_data_processing_service.py
cp backend/services/load_modeling_residential.py D:/cess-delivery/backend/services/load_modeling_residential.py
cp backend/services/load_modeling_industrial.py D:/cess-delivery/backend/services/load_modeling_industrial.py
```

- [ ] **Step 3: diff 验证 dev 与 delivery 一致**

```bash
diff backend/services/load_data_processing_service.py D:/cess-delivery/backend/services/load_data_processing_service.py
diff backend/services/load_modeling_residential.py D:/cess-delivery/backend/services/load_modeling_residential.py
diff backend/services/load_modeling_industrial.py D:/cess-delivery/backend/services/load_modeling_industrial.py
```

预期：全部无差异输出

- [ ] **Step 4: Commit 最终状态**

```bash
git add -A
git commit -m "feat: complete project directory structure optimization"
```
