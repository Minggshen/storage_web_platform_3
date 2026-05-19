# 项目架构文档

> 新开对话时加载此文档可快速理解项目整体结构。操作命令、环境变量和行为规范见 `CLAUDE.md`。

## 三层架构、六个工作流步骤

| Tier | 目录 | 技术栈 |
|------|------|--------|
| 1 — 前端 SPA | `frontend/` | React 19 + Vite 8 + TypeScript + Tailwind CSS 4 + pnpm 10 |
| 2 — 后端 API | `backend/` | Python 3.11 + FastAPI |
| 3 — 求解引擎 | `storage_engine_project/` | Python 3.11, CLI 独立进程 |

六个工作流步骤：① 项目总览 → ② 拓扑建模 → ③ 资产绑定 → ④ 构建校验 → ⑤ 计算运行 → ⑥ 结果展示。

---

## Tier 1: 前端 SPA

React Router v7，所有路由包在 `<ErrorBoundary>` 中。实际使用的公共组件：`ErrorBoundary`、`ErrorBanner`、`ConfirmDialog`、`ThemeToggle`、`StepBadge`（`components/common/`）。

**URL 路由：**

| Route | Page | Purpose |
|-------|------|---------|
| `/projects` | `ProjectsPage` | 项目列表 |
| `/projects/new` | `ProjectCreatePage` | 新建项目 |
| `/projects/:id/overview` | `ProjectOverviewPage` | 仪表盘 |
| `/projects/:id/topology` | `TopologyPage` | 拓扑编辑器 + 模板存取 |
| `/projects/:id/assets` | `AssetsPage` | 上传电价/设备/负荷数据 |
| `/projects/:id/build` | `BuildPage` | 编译 DSS → 求解器工作区 |
| `/projects/:id/solver` | `SolverPage` | GA 优化 + 安全-经济滑块 |
| `/projects/:id/results` | `ResultsPage` | Pareto 图/NPV/导出 |

所有页面在 `AppShell` 内（侧边栏 + 步骤条 + 内容区），dashboard 每 10s 轮询。API 调用使用 `services/http.ts` 中的 `http()` — `fetch` + `AbortController` 超时（默认 60s）。

**步骤式布局：** 全部 6 个页面使用 `StepBadge` 组件标注步骤编号 ①②③④。

| Page | Steps |
|------|-------|
| ProjectOverviewPage | ① 项目概况 → ② 状态&摘要 → ③ 流程进度 |
| TopologyPage | ① 选择模板 → ② 全局经济参数 → ③ 配电网拓扑建模 → ④ 潮流模型预览 |
| AssetsPage | ① 电价表 → ② 设备策略库 → ③ 负荷数据导入 |
| BuildPage | ① 构建Workspace → ② 编译验证 → ③ 电网诊断 → ④ 输出文件预览(可折叠) |
| SolverPage | ① 参数配置 → ② 运行控制 → ③ 任务信息 → ④ 日志输出 |
| ResultsPage | ① 方案摘要 → ② 可行性验证 → ③ 配电网评估 → ④ 详细分析 |

### 各页面关键行为

**TopologyPage：** 保存功能分拆——步骤②有单独的"保存经济参数"按钮，步骤③有"保存拓扑"+"保存为模板"按钮。两者独立跟踪保存状态。经济参数区域始终展开、4 列 grid。该页面使用 inline style；其他页面使用 Tailwind CSS。

**AssetsPage 步骤③：** 上传原始负荷 Excel（两列：时间+负荷），点击"一键处理"调用 `POST /api/assets/process-runtime`（SSE 流式）。后端跑 KMeans 聚类建模 → build_runtime 转换 → 逐节点资产注册。日志面板显示进度条和逐节点状态；文件预览面板展示 PNG 图表和 runtime CSV。badge 在全部上传+全部处理完成后才变绿，否则橙色。每个已上传节点有 × 删除按钮。

**BuildPage：** 步骤①双列 grid（`1fr 1.5fr`）——build preview 和 solver workspace，等高（`maxHeight: 530px`，`overflow-y: auto`）。步骤③自动 service lines 和容量表默认折叠、点击标题展开。电网健康检查用 `PctBar` 组件，颜色编码绿/黄/红。

**SolverPage：** 安全-经济滑块（0–100），左=经济(红)、右=安全(绿)，渐变条实时显示百分比。运行中滑块冻结在任务实际值。stdout 和 stderr 日志面板统一样式——始终显示 `<pre>` 块，无占位符。

---

## Tier 2: FastAPI 后端

入口 `storage_fastapi_backend.py`。CORS 通过 `CORS_ALLOW_ORIGINS` 环境变量配置。`GET /health` 健康检查。

五组路由（`backend/routes/`）：`project.py`、`topology.py`、`assets.py`、`build.py`、`solver.py`。

业务逻辑在 `backend/services/`（23 个模块）。Pydantic schema 在 `backend/models/`。项目持久化为 `backend/data/projects/{id}/project.json`。

### 拓扑模板

模板存放在 `backend/data/topology_templates/`（JSON 文件）。端点：`GET /api/topology/templates`（列表）、`POST /api/topology/templates`（保存，带名称+描述+拓扑）、`GET /api/topology/templates/{id}`（详情）、`DELETE /api/topology/templates/{id}`。

### 负荷数据处理管道（AssetsPage 步骤③）

关键模块：`load_data_processing_service.py`、`load_modeling_residential.py`、`load_modeling_industrial.py`、`build_runtime_residential.py`、`build_runtime_industrial.py`（后四个原为根目录 `scripts/` 下的中文文件名脚本，已迁移并重命名）。

端点：
- `POST /api/assets/raw-load-data/upload` — 上传原始 Excel，保存为 `raw_load_data/{node}/raw_load_data.xlsx`
- `GET /api/assets/raw-load-data/uploaded/{project_id}` — 列出已上传和已处理节点
- `DELETE /api/assets/raw-load-data/{project_id}/{node_id}` — 删除原始数据和建模产物
- `POST /api/assets/process-runtime` — SSE 流式一键处理
- `GET /api/assets/preview/{project_id}/{node_id}` — 列出可预览文件
- `GET /api/assets/preview/{project_id}/{node_id}/{file_name}` — 获取文件内容（PNG/CSV/TXT）

处理流程：原始 Excel 上传 → `glob("*.xlsx")` 查找 → 调用建模脚本（居民用 `load_modeling_residential.py`、工商业用 `load_modeling_industrial.py`，KMeans 聚类）→ 输出到 `modeling_output/{node}/` → 调用 build_runtime 脚本读取中间 Excel 生成 runtime CSV 到 `assets/runtime/{node}/` → 注册到 `project.assets` 并绑定拓扑节点。所有中间产物保留（不自动删除）。

### 项目目录结构

```
{project_id}/
├── project.json                       ← 工程级：拓扑、资产、绑定
├── assets/
│   ├── tariff/                        ← ① 电价表（工程级）
│   ├── device_library/                ← ② 设备策略库（工程级）
│   └── runtime/{node}/                ← ③ 最终 runtime CSV（节点级）
│       ├── runtime_year_model_map.csv
│       └── runtime_model_library.csv
├── raw_load_data/{node}/              ← ③ 原始上传 Excel（节点级）
│   └── raw_load_data.xlsx
├── modeling_output/{node}/            ← ③ 建模产物（节点级，全部保留）
├── build/                             ← ④ 构建产物（工程级模板）
│   ├── inputs/dss/visual_model/       ←    OpenDSS 电路文件
│   ├── solver_handoff/dss/            ←    DSS 交接副本
│   ├── solver_workspace/inputs/       ←    求解器输入模板（含 node_loads、tariff、storage、registry）
│   ├── manifest/build_manifest.json
│   └── solver_command.json
└── solver_runs/task_{id}/             ← ⑤ 求解任务快照（任务级，独立完整副本）
    ├── stdout.log / stderr.log
    └── solver_workspace/outputs/      ←    结果文件
```

工程级文件在所有求解任务间共享；任务级目录自包含，允许多次求解共存不互相影响。DSS 电路在 `build/` 下有三份副本（inputs / solver_handoff / solver_workspace）——这是管道步骤间的有意隔离，不是冗余 bug。

### 安全

- `file_store.py`：上传文件名通过 `Path(name).name` 消毒，防止路径穿越
- `solver_execution_service.py` 和 `build_export_service.py`：构造路径前验证 `project_id`（拒绝 `..`、`/`、`\`）

### 静态文件

若 `backend/static/` 存在（Vite 输出目标），FastAPI 挂载并做 SPA fallback；`index.html` 响应头 `Cache-Control: no-cache`，`/assets/*` 设为 `public, max-age=31536000, immutable`。

---

## Tier 3: 求解引擎

CLI 独立应用，入口 `storage_engine_project/main.py`。

统一日志：`logging_config.py` → `get_logger(name)` → stdout + `logs/solver.log`（每日轮转）。

**优化循环：**
1. `LemmingOptimizer`（多目标 GA）生成候选储能配置
2. `StorageFitnessEvaluator` 跑年度仿真 + 财务模型
3. `AnnualOperationKernel` → `DayAheadScheduler` → `RollingDispatchController`
4. 可选 `OpenDSSConstraintOracle` 通过 COM 校验电压/线路限制

GA 完成后，`pareto_utils.py` 中的 `select_best_compromise()` 从 Pareto 归档中选出最终方案。选择使用四项归一化指标（Pareto 距离、回收期、安全性、NPV），权重由 `--safety-economy-tradeoff` 控制（0=纯经济，1=纯安全，默认 0.5）。前端通过 SolverPage 上的滑块暴露此参数。

**关键模块：** `optimization/`（GA 引擎 + Pareto 选择）、`simulation/`（调度）、`economics/`（全生命周期 NPV/IRR）、`data/`（场景构建器）、`config/`（dataclass 配置）、`visualization/`（matplotlib 绘图）。

### 已知问题

- `StorageFitnessEvaluator._maybe_cache()` 对 `full_recheck` 和 `full_year` 模式跳过缓存——这些结果包含 365 天 OpenDSS 网络追踪数据（每小时每场景的母线电压、线路电流），`deepcopy` 导致 `MemoryError`。仅轻量的 `fast_proxy` 结果（14 个代表日，无详细网络追踪）被缓存。不影响结果输出——`export_optimization_run()` 仍然将所有结果写入磁盘。缓存使用 `_clone_result()` → `deepcopy()`；若新增缓存模式，确保结果对象足够轻量。

---

## 交付模式

`start.bat` 是最终用户入口——零环境引导：自动检测 Python，按需下载便携 Python 3.11，创建本地 venv，安装依赖，启动 uvicorn。预构建的前端在 `backend/static/` 中，由 FastAPI 直接提供服务，无需 Node.js。

开发仓库：`D:\storage_web_platform_3`，交付仓库：`D:\cess-delivery`（独立）。

`create-delivery-repo.ps1` 生成交付包，复制 `backend/models/`、`backend/services/`、`backend/routes/`、`backend/static/`、`storage_engine_project/**/*.py`、`start.bat`、`pyproject.toml`、`.env.example`。

**同步注意事项：**
- `cp`/`rsync` 在 bash 沙箱中可能静默失败——使用 Python `shutil.copy2` 或 Write 工具
- `storage_engine_project/` 有改动时必须整目录同步——部分同步会导致 API 签名不匹配
- 同步 Python 文件后必须重启 uvicorn
- `npx`/`pnpm` 需要 `export PATH="$ORIGINAL_PATH:/c/Users/M/AppData/Local/pnpm:/c/Program Files/nodejs"`
- Git 的 `-C` 参数需要 Windows 风格路径（`D:/repo`），而非 `/d/repo`
