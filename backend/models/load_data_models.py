from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RawLoadDataUploadResponse(BaseModel):
    success: bool
    node_id: str
    file_name: str
    stored_path: str


class ProcessRuntimeRequest(BaseModel):
    project_id: str
    node_ids: List[str] = Field(..., min_length=1)


class PreviewFileInfo(BaseModel):
    name: str
    type: str  # "image" | "csv" | "text"
    url: str


class PreviewNodeResponse(BaseModel):
    node_id: str
    files: List[PreviewFileInfo]
