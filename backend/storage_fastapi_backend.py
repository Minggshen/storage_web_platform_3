
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.assets import router as assets_router
from routes.build import router as build_router
from routes.project import router as project_router
from routes.topology import router as topology_router
from routes.solver import router as solver_router

app = FastAPI(
    title="Storage Visual Modeling Backend",
    description=(
        "工作流接口增强版：补齐前端页面化工作流所需的项目列表/创建、项目总览聚合、整拓扑提交、"
        "搜索边界推导表、任务日志等接口，配合图形化建模前端使用。"
    ),
    version="2.6.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root() -> dict:
    return {
        "success": True,
        "message": "Storage visual modeling backend is running.",
        "phase": "workflow-api-enhancement",
        "version": "2.6.0",
        "frontend_usage": (
            "前端应通过 /api/projects、/api/project/:id/dashboard、/api/topology、/api/assets、"
            "/api/build、/api/solver 接口完成完整工作流。"
        ),
    }

@app.get("/health")
def health() -> dict:
    return {"success": True, "status": "ok", "version": "2.6.0"}

app.include_router(project_router)
app.include_router(topology_router)
app.include_router(assets_router)
app.include_router(build_router)
app.include_router(solver_router)
