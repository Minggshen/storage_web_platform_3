# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Architecture & codebase details:** see `docs/architecture.md`.

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

## Key Files & Directories

| Path | Purpose |
|------|---------|
| `frontend/src/pages/workspace/` | 6 workflow page components |
| `frontend/src/services/` | API call functions (`http.ts`, `assets.ts`, `solver.ts`, etc.) |
| `frontend/src/components/common/` | Shared components: `ErrorBoundary`, `ErrorBanner`, `ConfirmDialog`, `ThemeToggle`, `StepBadge` |
| `backend/routes/` | 5 route modules: `project.py`, `topology.py`, `assets.py`, `build.py`, `solver.py` |
| `backend/services/` | Business logic (23 modules) |
| `backend/models/` | Pydantic schemas |
| `backend/data/projects/{id}/` | Per-project JSON + assets |
| `storage_engine_project/main.py` | Solver engine CLI entry |
| `docs/superpowers/specs/` | Design specs |
| `docs/superpowers/plans/` | Implementation plans |

## URL Routes (Frontend)

| Route | Page |
|-------|------|
| `/projects` | `ProjectsPage` |
| `/projects/new` | `ProjectCreatePage` |
| `/projects/:id/overview` | `ProjectOverviewPage` |
| `/projects/:id/topology` | `TopologyPage` |
| `/projects/:id/assets` | `AssetsPage` |
| `/projects/:id/build` | `BuildPage` |
| `/projects/:id/solver` | `SolverPage` |
| `/projects/:id/results` | `ResultsPage` |

All pages wrapped in `<AppShell>` (sidebar + 6-step stepper + content). Dashboard polls every 10s. API timeout via `VITE_API_TIMEOUT_MS` (default 60s).

## Three Tiers

1. **Frontend SPA** — React 19 + Vite 8, step-based layout using `StepBadge` (①②③④)
2. **FastAPI Backend** — 5 route modules, 23 service modules, JSON persistence
3. **Solver Engine** — CLI app (`storage_engine_project/main.py`), GA optimization + OpenDSS oracle

## Delivery

**Dev repo:** `D:\storage_web_platform_3` · **Delivery repo:** `D:\cess-delivery`

`start.bat` bootstraps from zero (auto-detect Python, venv, deps, uvicorn). Pre-built frontend in `backend/static/` served by FastAPI — no Node.js needed.

**Sync to delivery:** `cp`/`rsync` silently fail in bash sandbox. Use Python `shutil.copy2` for bulk, or `Write` tool for single files. When `storage_engine_project/` changes, sync the ENTIRE directory — partial sync breaks API signatures. After syncing Python files, restart uvicorn.

## Environment Variables

**Backend** (`.env.example`): `CORS_ALLOW_ORIGINS`, `LOG_LEVEL`, `LOG_DIR`, `STORAGE_OPENDSSCONSTRAINTORACLE_ENABLED`, `STORAGE_DSS_MASTER_PATH`, `STORAGE_OPENDSS_TARGET_BUS`, `STORAGE_OPENDSS_VOLTAGE_LIMIT_PU`

**Frontend** (`frontend/.env.example`): `VITE_API_BASE_URL` (dev: `http://127.0.0.1:8000`, delivery: empty), `VITE_API_TIMEOUT_MS` (default: `60000`)

## Bash Sandbox Gotchas

- Bash returns no stdout. Redirect to file (`> file.txt 2>&1`) then `Read`.
- `cp`/`rsync` may silently fail — use `Write` tool or Python `shutil.copy2`.
- `npx`/`pnpm` require: `export PATH="$ORIGINAL_PATH:/c/Users/M/AppData/Local/pnpm:/c/Program Files/nodejs"`
- Git `-C` flag needs Windows paths: `D:/repo` not `/d/repo`.

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
