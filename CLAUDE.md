# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Frontend** (`frontend/` — React 19 + Vite 8 + TypeScript, pnpm 10):

| Command | What it does |
|---------|---------------|
| `pnpm dev` | Vite dev server on port 5173 |
| `pnpm build` | `tsc -b` then `vite build` → outputs directly to `backend/static/` (via `build.outDir`) |
| `pnpm lint` | ESLint on `*.{ts,tsx}` |
| `pnpm preview` | Preview production build locally |

**Backend** (Python 3.11, FastAPI):

```bash
pip install -e ".[full,dev]"        # all deps (engine + web + test)
cd backend && uvicorn storage_fastapi_backend:app --host 0.0.0.0 --port 8000
```

**Lint / typecheck** (run from repo root):

```bash
ruff check storage_engine_project/ backend/
mypy storage_engine_project/ --ignore-missing-imports
```

**Tests**: `pytest>=9.0` is in `[dev]` deps but no test suite exists yet.

**CI**: GitHub Actions on push/PR to `main` — frontend (lint → typecheck → build) and backend (ruff → mypy).

**Bash sandbox**: In the Codex IDE environment, the Bash tool consistently returns no stdout. Workaround: redirect output to a file (`> path/to/file.txt 2>&1`) then Read the file. `cp` and `rsync` commands may silently fail; use `Write` tool or Python `shutil.copy2` for file copy operations. `npx`/`pnpm` require `export PATH="$ORIGINAL_PATH:/c/Users/M/AppData/Local/pnpm:/c/Program Files/nodejs"` before use. Git commands with `-C` flag need Windows-style paths (`D:/repo`) not `/d/repo`.

**Design specs**: Live under `docs/superpowers/specs/` — e.g. `2026-05-15-frontend-layout-redesign-design.md` documents the step-based layout system in detail.

## Architecture

Three tiers, six workflow steps.

### Tier 1: Frontend SPA (`frontend/src/`)

React Router v7. Every route is wrapped in `<ErrorBoundary>` (per-page + root-level fallback). Common components that are actually used: `ErrorBoundary`, `ErrorBanner`, `ConfirmDialog`, `ThemeToggle`, `StepBadge` (in `components/common/`). All other common components have been removed as dead code.

URL structure:

| Route | Page | Purpose |
|-------|------|---------|
| `/projects` | `ProjectsPage` | Project list with delete confirmation |
| `/projects/new` | `ProjectCreatePage` | Create project |
| `/projects/:id/overview` | `ProjectOverviewPage` | Dashboard |
| `/projects/:id/topology` | `TopologyPage` | Visual topology editor with template save/load |
| `/projects/:id/assets` | `AssetsPage` | Upload tariffs, devices, runtime loads |
| `/projects/:id/build` | `BuildPage` | Compile → solver workspace |
| `/projects/:id/solver` | `SolverPage` | Run GA optimization with safety-economy slider |
| `/projects/:id/results` | `ResultsPage` | Pareto charts, NPV, export |

All pages sit inside `AppShell` (sidebar + stepper bar + content area, dashboard polls every 10s to keep step status in sync). API calls use `http()` in `services/http.ts` — `fetch` + `AbortController` timeout (default 60s, via `VITE_API_TIMEOUT_MS`). `VITE_API_BASE_URL` defaults to `''` (same-origin for delivery mode).

Solver UX: parameters freeze to show actual run values while a task is active; a running indicator (pulse dot) replaces the "启用求解" button. ResultsPage shows an amber banner when solver is running.

Safety-economy slider: a range input (0–100) on SolverPage controls `safety_economy_tradeoff`. Left = economy (红色), right = safety (绿色), gradient bar from red via amber to green. The slider shows real-time percentage split (e.g. "经济性 70% / 安全性 30%"). A text label summarizes the current position: 纯经济最优 / 偏重经济 / 经济安全并重 / 偏重安全 / 纯安全最优. During a run the slider freezes at the task's actual value.

**Step-based layout**: All 6 workflow pages use numbered step indicators (①②③④) via the shared `StepBadge` component. Each page is organized into 2–4 logical steps guiding users sequentially:

| Page | Steps |
|------|-------|
| ProjectOverviewPage | ① 项目概况 → ② 状态&摘要 → ③ 流程进度 |
| TopologyPage | ① 选择模板 → ② 全局经济参数 → ③ 配电网拓扑建模 → ④ 潮流模型预览 |
| AssetsPage | ① 电价表 → ② 设备策略库 → ③ 负荷数据导入 |
| BuildPage | ① 构建Workspace → ② 编译验证 → ③ 电网诊断 → ④ 输出文件预览(可折叠) |
| SolverPage | ① 参数配置 → ② 运行控制(进度+按钮合并) → ③ 任务信息 → ④ 日志输出 |
| ResultsPage | ① 方案摘要 → ② 可行性验证 → ③ 配电网评估 → ④ 详细分析 |

TopologyPage details: save functionality is split — step ② has a "保存经济参数" button (saves only `economic_parameters`), step ③ has "保存拓扑" + "保存为模板" buttons (saves nodes/edges). Both track save status reactively (显示"有未保存修改"/"已保存 HH:MM:SS"). Economic parameters are always expanded with fields in a 4-column grid (`repeat(4, 1fr)`), reference hints single-line with ellipsis. TopologyPage uses inline styles; other pages use Tailwind CSS.

AssetsPage step ③ details: Upload raw load Excel (two columns: time + load), then "一键处理" button calls `POST /api/assets/process-runtime` (SSE streaming). The backend runs KMeans clustering modeling → build_runtime conversion → asset registration per node. A log panel shows per-node status with progress bar; a file preview panel lets users view generated PNG charts and runtime CSVs. Badges show uploaded/processed counts — orange when incomplete, green only when all nodes are both uploaded AND processed. Each uploaded node has an × delete button. Status badge distinguishes actual file uploads from topology metadata declarations.

BuildPage details: step ① has a two-column grid (`1fr 1.5fr`) — build preview (narrower) and solver workspace (wider, both capped at `maxHeight: 530px` with `overflow-y: auto` for equal heights). Step ③ auto service lines and capacity tables are default-collapsed with click-to-expand headers. Grid health check results use `PctBar` (a horizontal percentage bar) for transformer overload ratio and per-recommendation loading_pct, color-coded green/amber/red.

SolverPage details: stdout and stderr log panels now have unified styling — both always show a `<pre>` block (no conditional placeholder).

### Tier 2: FastAPI Backend (`backend/`)

Entry: `storage_fastapi_backend.py`. CORS configured via `CORS_ALLOW_ORIGINS` env var (not wildcard `*`). Health check at `GET /health`.

Five route modules (`backend/routes/`): `project.py`, `topology.py`, `assets.py`, `build.py`, `solver.py`.

Business logic in `backend/services/` (23 modules). Key additions: `load_data_processing_service.py` (raw data upload → modeling → runtime CSV generation via SSE), `build_runtime_residential.py` / `build_runtime_industrial.py` (intermediate Excel → runtime CSV conversion), `load_modeling_residential.py` / `load_modeling_industrial.py` (KMeans clustering load modeling, originally under root `scripts/` with Chinese filenames). Pydantic schemas in `backend/models/` (including `load_data_models.py` for raw-load-data endpoints). Projects persist as JSON under `backend/data/projects/{id}/`.

**Topology templates**: The backend stores reusable network topology templates under `backend/data/topology_templates/` (JSON files). Endpoints: `GET /api/topology/templates` (list), `POST /api/topology/templates` (save with name + description + topology), `GET /api/topology/templates/{id}` (detail), `DELETE /api/topology/templates/{id}`. The TopologyPage step ① has a dropdown (saved templates + built-in IEEE 33) with a standalone "载入模板" button, and step ③ has a "保存为模板" button (opens name/description dialog).

**Load data processing pipeline** (AssetsPage step ③):

1. User uploads raw Excel per load node → `POST /api/assets/raw-load-data/upload` → saved as `raw_load_data/{node}/raw_load_data.xlsx`
2. "一键处理" → `POST /api/assets/process-runtime` (SSE) → `LoadDataProcessingService.process_all_nodes()`:
   - Finds raw xlsx via `glob("*.xlsx")` (supports legacy filenames from before normalization)
   - Calls `load_modeling_residential.py` or `load_modeling_industrial.py` → outputs to `modeling_output/{node}/`
   - Calls `build_runtime_residential.py` or `build_runtime_industrial.py` → reads from `modeling_output/{node}/`, writes to `assets/runtime/{node}/`
   - Registers runtime CSVs to `project.assets` + binds to topology node
   - All intermediate files preserved (xlsx/png/txt) — no automatic cleanup
3. Preview: `GET /api/assets/preview/{project_id}/{node_id}` → lists files; `GET /api/assets/preview/{project_id}/{node_id}/{file_name}` → serves PNG/CSV/TXT
4. Delete: `DELETE /api/assets/raw-load-data/{project_id}/{node_id}` → removes both `raw_load_data/{node}/` and `modeling_output/{node}/`

The modeling scripts use KMeans clustering: residential nodes → R01/R02 naming; industrial/commercial nodes → work-rest pattern (W/R/S) × annual peak-valley periods → (1,1) tuple naming. Scripts were originally under root `scripts/` with Chinese filenames; moved to `backend/services/` for proper module organization.

**Security**: `file_store.py` sanitizes uploaded filenames via `Path(name).name` to prevent path traversal. `solver_execution_service.py` and `build_export_service.py` validate `project_id` before path construction (reject `..`, `/`, `\`).

Static files: if `backend/static/` exists (Vite builds here directly), FastAPI mounts it with SPA catch-all. Otherwise root returns JSON health check.

**Project directory structure** (`backend/data/projects/{id}/`):

| Directory | Scope | Content |
|-----------|-------|---------|
| `project.json` | project-wide | Topology, assets, bindings, solver config |
| `assets/tariff/` | project-wide | ① Electricity price table |
| `assets/device_library/` | project-wide | ② Device strategy library |
| `assets/runtime/{node}/` | per-node | ③ Final runtime CSVs (`runtime_year_model_map.csv` + `runtime_model_library.csv`) |
| `raw_load_data/{node}/` | per-node | ③ Raw uploaded Excel (`raw_load_data.xlsx`) |
| `modeling_output/{node}/` | per-node | ③ Modeling artifacts (PNG charts + intermediate Excel; all preserved) |
| `build/` | project-wide | ④ Compiled OpenDSS circuit files + solver workspace template |
| `solver_runs/task_{id}/` | per-task | ⑤ Independent solver execution snapshot with results |

Design principle: project-wide files are shared across all solver tasks; per-task directories are self-contained snapshots so multiple solver runs can coexist without interference. The `build/solver_workspace/` is a template copied into each task. DSS files are duplicated in `build/inputs/dss/`, `build/solver_handoff/dss/`, and `build/solver_workspace/inputs/dss/` — this is intentional pipeline isolation, not a bug.

### Tier 3: Solver Engine (`storage_engine_project/`)

CLI application, independent of the web tier. Entry: `main.py`.

Unified logging via `logging_config.py` → `get_logger(name)` factory. Outputs to stdout + `logs/solver.log` (daily rotation). Log level via `LOG_LEVEL` env var. All `print()` calls migrated to `logger.info/debug/warning/error`.

Core optimization loop:
1. `LemmingOptimizer` (multi-objective GA) generates candidate storage configurations
2. `StorageFitnessEvaluator` runs annual simulation + financial model for each candidate
3. `AnnualOperationKernel` calls `DayAheadScheduler` → `RollingDispatchController`
4. Optional `OpenDSSConstraintOracle` validates voltage/line limits via COM

After GA completes, `select_best_compromise()` in `pareto_utils.py` picks the final scheme from the Pareto archive. The selection uses four normalized criteria (Pareto distance, payback, safety, NPV) with weights controlled by `--safety-economy-tradeoff` (0 = pure economy, 1 = pure safety, default 0.5). The frontend exposes this via a slider on SolverPage.

Key modules: `optimization/` (GA engine + Pareto selection), `simulation/` (dispatch), `economics/` (lifecycle NPV/IRR), `data/` (scenario builder), `config/` (dataclass configs), `visualization/` (matplotlib plots).

**Known engine issues:**

- `StorageFitnessEvaluator._maybe_cache()` skips caching for `full_recheck` and `full_year` modes — these results carry 365-day OpenDSS network traces (bus voltages, line currents per hour × per scenario), and `deepcopy` on them causes `MemoryError`. Only `fast_proxy` results (14 representative days without detailed network traces) are cached. This does not affect result output — `export_optimization_run()` writes all results to disk regardless of caching.
- The cache uses `_clone_result()` → `deepcopy()`. If adding new cached modes, ensure the result objects are lightweight enough for deep copy.

### Delivery mode

`start.bat` is the end-user entry point — zero-environment bootstrap: auto-detects Python, downloads portable Python 3.11 if needed, creates local venv, installs deps, starts uvicorn. The pre-built frontend in `backend/static/` is served by FastAPI. No Node.js required for delivery. The delivery repo is at `D:\cess-delivery` (separate from this dev repo).

The `create-delivery-repo.ps1` script generates the delivery package. It copies `backend/models/`, `backend/services/`, `backend/routes/`, `backend/static/`, `storage_engine_project/**/*.py`, `start.bat`, `pyproject.toml`, `.env.example`.

**Delivery sync caveats:** `cp` commands silently fail in the bash sandbox. Use `Write` tool for single files (read dev first, then write to delivery) or Python `shutil.copy2` for bulk sync. When `storage_engine_project/` files change, sync the entire directory — partial sync causes mismatched API signatures (e.g., `main.py` passing `safety_economy_tradeoff` to an older `LemmingOptimizer` that doesn't accept it). After syncing Python files, restart uvicorn for changes to take effect.

### Environment variables

**Backend** (`.env.example`):
- `CORS_ALLOW_ORIGINS` — comma-separated origins (default: `http://localhost:5173,http://127.0.0.1:5173`)
- `LOG_LEVEL` — `DEBUG` / `INFO` / `WARNING` / `ERROR` (default: `INFO`)
- `LOG_DIR` — log output directory (default: `logs/`)
- `STORAGE_OPENDSSCONSTRAINTORACLE_ENABLED` — enable OpenDSS COM oracle (default: `false`)
- `STORAGE_DSS_MASTER_PATH` — path to Master.dss for OpenDSS
- `STORAGE_OPENDSS_TARGET_BUS` / `STORAGE_OPENDSS_VOLTAGE_LIMIT_PU`

**Frontend** (`frontend/.env.example`):
- `VITE_API_BASE_URL` — dev: `http://127.0.0.1:8000`, delivery: empty for same-origin
- `VITE_API_TIMEOUT_MS` — request timeout in ms (default: `60000`)

## Behavioral Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
