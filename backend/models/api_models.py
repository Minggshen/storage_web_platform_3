from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ValidationCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class ValidationSummary(BaseModel):
    ok: bool
    validation_id: str
    scene_name: str
    saved_dir: str
    files: Dict[str, Optional[str]]
    checks: List[ValidationCheck]
    warnings: List[str] = Field(default_factory=list)
    summaries: Dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    validation_id: str = Field(..., description="/api/project/validate 返回的 validation_id")
    project_name: str = Field(default="配电网储能优化网页平台")
    scene_name: str = Field(default="node09_联合汽车电子有限公司芜湖分公司")
    optimizer: str = Field(default="pareto")
    dispatch_mode: str = Field(default="annual_daily")
    safety_first: bool = Field(default=True)
    plot_enabled: bool = Field(default=True)
    strict_tariff: bool = Field(default=True)
    opendss_enabled: bool = Field(default=True)
    advanced_visible: bool = Field(default=True)
    use_mock_result: bool = Field(default=True)


class RunResponse(BaseModel):
    ok: bool = True
    task_id: str
    status: str
    progress: int
    message: str


class TaskStatusResponse(BaseModel):
    ok: bool = True
    task_id: str
    status: str
    progress: int
    result_ready: bool
    validation_id: str
    scene_name: str
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    logs: List[str]
    error: Optional[str] = None


class TaskResultResponse(BaseModel):
    ok: bool = True
    task_id: str
    result: Dict[str, Any]