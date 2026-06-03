from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes.assets import router as assets_router
from routes.build import router as build_router
from routes.project import router as project_router
from routes.topology import router as topology_router
from routes.solver import router as solver_router

APP_VERSION = "2.6.0"

app = FastAPI(
    title="Storage Visual Modeling Backend",
    description=(
        "工作流接口增强版：补齐前端页面化工作流所需的项目列表/创建、项目总览聚合、整拓扑提交、"
        "搜索边界推导表、任务日志等接口，配合图形化建模前端使用。"
    ),
    version=APP_VERSION,
)

_cors_origins_raw = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Cache-Control"],
)


@app.middleware("http")
async def _cache_control_middleware(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

_static_dir = Path(__file__).parent / "static"
_has_frontend = _static_dir.is_dir()

@app.get("/health")
def health() -> dict:
    return {"success": True, "status": "ok", "version": APP_VERSION}


app.include_router(project_router)
app.include_router(topology_router)
app.include_router(assets_router)
app.include_router(build_router)
app.include_router(solver_router)

if _has_frontend:
    _static_root = _static_dir.resolve()

    def _is_within_static_root(path: Path) -> bool:
        resolved = path.resolve()
        return resolved == _static_root or _static_root in resolved.parents

    # JS/CSS/字体等静态资源
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    # Favicon
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        return FileResponse(str(_static_dir / "favicon.svg"), headers={"Cache-Control": "no-cache"})

    # SPA fallback: 所有非 API 的 GET 请求返回 index.html（必须在 API 路由之后）
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        requested = (_static_dir / full_path).resolve()
        if not _is_within_static_root(requested):
            return FileResponse(str(_static_dir / "index.html"), headers={"Cache-Control": "no-cache"})
        if requested.is_file():
            return FileResponse(str(requested))
        return FileResponse(str(_static_dir / "index.html"), headers={"Cache-Control": "no-cache"})
else:
    @app.get("/")
    def root() -> dict:
        return {
            "success": True,
            "message": "Storage visual modeling backend is running.",
            "version": APP_VERSION,
        }
