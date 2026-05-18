# Runtime 数据处理一体化 · 设计文档

**日期**: 2026-05-18
**状态**: 待审阅

## 1. 目标

将资产绑定页面 Step ③（Runtime 文件绑定）从"上传已预处理的 runtime CSV"改为"上传原始负荷数据 + 一键自动处理"，降低用户的手工预处理成本。

## 2. 用户流程

1. 用户在 Step ③ 选择负荷节点，上传该节点的原始用电数据 Excel（两列：时间 + 负荷）
2. 重复步骤 1，直到所有需要的负荷节点都已上传
3. 点击"一键处理"按钮
4. 后端根据各节点的 `category` 自动选择对应脚本批量处理
5. 日志栏通过 SSE 实时推送处理进度
6. 处理完成后自动注册 runtime 文件到 `project.assets`，侧边栏状态联动更新
7. 用户可在文件预览区切换节点，查看生成的 PNG 图表和 CSV 表格

## 3. 文件存储路径

处理产物统一存放在项目目录下，删除项目时一并清理：

```
project_dir/
├── raw_load_data/                       ← 新增
│   └── {node_id}/
│       ├── raw_load_data.xlsx           ← 用户上传的原始 Excel
│       ├── 01_全年逐日模型映射表.xlsx    ← 建模中间产物（居民）
│       ├── 02_居民典型日模型库.xlsx
│       ├── 03_聚类评估结果.xlsx
│       ├── 01_居民典型日曲线.png         ← 图表（可预览）
│       ├── 02_全年逐日模型映射.png
│       ├── 03_模型月度分布.png
│       └── 04_结果说明.txt
├── assets/
│   └── runtime/                         ← 现有：最终 runtime CSV
│       └── {node_id}/
│           ├── runtime_year_model_map.csv
│           └── runtime_model_library.csv
└── project.json                         ← assets 字段自动注册
```

- 原始数据 + 中间产物 → `raw_load_data/{node_id}/`
- 最终 CSV → `assets/runtime/{node_id}/`，注册到 `project.assets`，与现有上传逻辑完全一致

## 4. API 设计

### 4.1 上传原始负荷数据

```
POST /api/assets/{project_id}/raw-load-data
Content-Type: multipart/form-data

Parameters:
  node_id: string   — 负荷节点 ID
  file: binary      — 原始用电数据 Excel

Response 200:
{
  "success": true,
  "node_id": "load_01",
  "file_name": "load_01_company.xlsx",
  "stored_path": "..."
}
```

### 4.2 一键批量处理（SSE）

```
POST /api/assets/{project_id}/process-runtime
Content-Type: application/json

Body: { "node_ids": ["load_01", "load_02", ...] }

Response (text/event-stream):
  {"type":"start","total":33}
  {"type":"progress","node":"load_01","step":"modeling","message":"正在进行 KMeans 聚类..."}
  {"type":"progress","node":"load_01","step":"convert","message":"已生成 runtime_year_model_map.csv"}
  {"type":"done","node":"load_01","charts":["01_居民典型日曲线.png","02_全年逐日模型映射.png"]}
  {"type":"error","node":"load_05","message":"缺少必要列：日期"}
  {"type":"complete","total":33,"success":32,"failed":1}
```

- 同步阻塞处理（逐个节点串行），每个节点处理完推送 `done`/`error` 事件
- 前端展示实时日志 + 进度条
- 处理过程中不阻塞其他 API 请求（SSE 是独立连接）

### 4.3 预览文件列表 & 内容

```
GET /api/assets/{project_id}/preview/{node_id}

Response 200:
{
  "node_id": "load_01",
  "files": [
    {"name": "01_居民典型日曲线.png", "type": "image", "url": "/api/assets/..."},
    {"name": "runtime_year_model_map.csv", "type": "csv", "url": "/api/assets/..."},
    ...
  ]
}

GET /api/assets/{project_id}/preview/{node_id}/{file_name}
→ 返回文件内容（图片直接 binary，CSV 返回 JSON rows）
```

## 5. 前端改造（AssetsPage Step ③）

布局从当前双栏改为三区纵向结构：

```
┌─────────────────────────────────────────────────┐
│ ③ Runtime 文件绑定   │ 已上传 15/33 · 已处理 0/33 │
├─────────────────────────────────────────────────┤
│ ┌── 上传原始数据 ──────────────────────────────┐ │
│ │ 选择负荷节点 [▼]  📁 选择文件  [上传]         │ │
│ │ 已上传节点：load_01 ✓ load_02 ✓ load_05 ...  │ │
│ │ 未上传节点：load_03 load_04 ...              │ │
│ │                               [一键处理 →]   │ │
│ └──────────────────────────────────────────────┘ │
│ ┌── 处理日志 ──────────────────────────────────┐ │
│ │ [✓] load_01 处理完成                         │ │
│ │ (自动滚动，最多保留最近 50 条)                 │ │
│ │ ━━━━━━━━━━━━━░░░░ 12/33                      │ │
│ └──────────────────────────────────────────────┘ │
│ ┌── 文件预览 ──────────────────────────────────┐ │
│ │ 选择节点 [▼]  选择文件 [▼]                    │ │
│ │ ┌──────────────────────────────────┐         │ │
│ │ │  图片预览 / CSV 表格预览          │         │ │
│ │ └──────────────────────────────────┘         │ │
│ └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## 6. 后端处理逻辑

### 6.1 新增服务 `load_data_processing_service.py`

```
backend/services/load_data_processing_service.py
```

核心流程：

```python
def process_node(node_id: str, category: str, project_dir: Path) -> ProcessResult:
    raw_dir = project_dir / "raw_load_data" / node_id
    runtime_dir = project_dir / "assets" / "runtime" / node_id

    # 1. 根据 category 选择建模脚本
    if category == "residential":
        model_dir = run_residential_modeling(raw_dir)
        build_runtime(model_dir, runtime_dir)
    else:
        model_dir = run_industrial_modeling(raw_dir)
        build_runtime(model_dir, runtime_dir)

    # 2. 注册 runtime CSV 到 project.assets（模拟 UploadFile 流程）
    register_runtime_asset(project, node_id, runtime_dir / "runtime_year_model_map.csv", "year_map")
    register_runtime_asset(project, node_id, runtime_dir / "runtime_model_library.csv", "model_library")
    bind_runtime_assets(project, node_id, year_map_asset, model_library_asset)
    save_project(project)
```

**与现有上传流程的兼容**：

当前 `save_asset_upload()` 仅接受 FastAPI `UploadFile` 对象。处理脚本生成的是磁盘文件，需要在 `ProjectModelService` 新增 `register_asset_file()` 方法：

```python
def register_asset_file(
    self,
    project_id: str,
    file_path: Path,         # 已存在的文件路径
    category: str,
    subfolder: str | None = None,
    metadata: dict | None = None,
) -> tuple[AssetRef, ProjectModel, Path]:
```

该方法直接注册已有文件到 `project.assets`，跳过文件复制步骤。其余 metadata 结构（`category`, `subfolder`, `runtime_kind`, `node_id`, `is_current`）与手动上传完全一致，确保 `dashboard_service` 的 `runtime_uploaded` 计数和侧边栏对勾逻辑无需额外适配。

    # 1. 根据 category 选择建模脚本
    if category == "residential":
        model_dir = run_residential_modeling(raw_dir)   # 原始 Excel → 中间 Excel + 图表
        build_runtime(model_dir, runtime_dir)            # 中间 Excel → runtime CSV
    else:
        model_dir = run_industrial_modeling(raw_dir)
        build_runtime(model_dir, runtime_dir)

    # 2. 注册 runtime CSV 到 project.assets
    register_runtime_assets(project, node_id, runtime_dir)
```

- 脚本内部硬编码路径已改为函数参数传入
- 处理单个节点失败不影响其他节点（try/except 并返回 error 事件）

### 6.2 依赖项

`pyproject.toml` 添加：
```
scikit-learn>=1.7,<2.0
```

`matplotlib` 已在 `[engine]` / `[full]` 可选依赖中，无需额外添加。

## 7. 脚本改造

`scripts/` 目录下 4 个脚本的状态：

| 脚本 | 改造方式 |
|------|---------|
| `全年逐日典型日聚类1h级居民负荷建模.py` | 提取核心函数，`ROOT_DIR` 改为参数传入 |
| `按工休和年用电峰谷分析的1h级工商业负荷建模_改.py` | 同上 |
| `build_runtime_files_residential.py` | `ROOT_DIR` 改为参数传入 |
| `build_runtime_files_industrial_or_commercial.py` | `ROOT_DIR` 改为参数传入 |

每个脚本的 `main()` 入口级逻辑保留（可独立运行），新增函数签名为接收参数路径的接口。

添加 `scripts/__init__.py` 使其可被 backend import。

## 8. 与现有系统的衔接

- **侧边栏对勾**：处理完成后自动注册 `project.assets`，dashboard 的 `runtime_uploaded` 计数自动更新（复用上一轮修复的逻辑）
- **构建校验**：不需要额外改动，runtime CSV 作为 `project.assets` 的一部分，构建流程可直接读取
- **资产删除**：删除项目时 `project_dir` 整体删除，`raw_load_data/` 同时清除

## 9. 启动文件修改

`start.bat` 需更新两处：

**（a）依赖安装**（第 113 行 fallback 命令）：
```batch
:: Before
"!PYTHON_EXE!" -m pip install fastapi uvicorn "pydantic>=2" python-multipart numpy scipy pandas openpyxl pywin32 joblib --quiet 2>&1
:: After
"!PYTHON_EXE!" -m pip install fastapi uvicorn "pydantic>=2" python-multipart numpy scipy pandas openpyxl pywin32 joblib scikit-learn --quiet 2>&1
```

**（b）预检模块**（第 143 行）：
```batch
:: Before
"!PYTHON_EXE!" -c "import fastapi, uvicorn, numpy, pandas; print('  Core modules OK')" 2>&1
:: After
"!PYTHON_EXE!" -c "import fastapi, uvicorn, numpy, pandas, sklearn; print('  Core modules OK')" 2>&1
```

`scikit-learn` 同时也加入 `pyproject.toml` 的 `[dependencies]`（供 `pip install -e ".[full]"` 路径自动安装），并在 `[full]` optional-dependencies 中也显式列出（供开发环境 `pip install -e ".[full]"`）。

`scripts/` 和 `backend/` 是同级目录。在 `backend/services/load_data_processing_service.py` 中 import 脚本模块时，需确保 Python 能找到 `scripts/` 包。

方案：在 `pyproject.toml` 的 `[tool.setuptools.packages.find]` 中新增 `scripts*`：

```
include = ["storage_engine_project*", "backend*", "scripts*"]
```

同时添加 `scripts/__init__.py`。安装后 `from scripts.build_runtime_files_residential import process_one_node_dir` 即可正常导入。

## 10. 验证方案

1. `pnpm build` — 前端构建通过
2. Python 语法检查 — 所有 `.py` 通过 `ast.parse`
3. 功能测试：
   - 上传居民节点原始数据 → 一键处理 → 日志显示成功 → 侧边栏计数更新
   - 上传工商业节点原始数据 → 一键处理 → 生成正确的 `(1,1)` 式组合模型编号
   - 上传格式错误的文件 → 日志显示失败原因
   - 预览区切换节点 → 正确加载对应图表和 CSV
   - 上传完所有节点 → 侧边栏打勾
