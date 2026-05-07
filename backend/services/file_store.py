from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import HTTPException, UploadFile

APP_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = APP_DIR / "backend_runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
EXPORT_DIR = RUNTIME_DIR / "exports"

for directory in (RUNTIME_DIR, UPLOAD_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

ALLOWED_SUFFIXES = {
    "registry": {".xlsx", ".xls", ".csv"},
    "tariff": {".xlsx", ".xls", ".csv"},
    "storage": {".xlsx", ".xls"},
    "runtime": {".xlsx", ".xls", ".csv", ".zip"},
    "dss": {".dss", ".txt", ".zip"},
}


async def save_upload(file: Optional[UploadFile], target_dir: Path, kind: str) -> Optional[Path]:
    if file is None:
        return None

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES[kind]:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES[kind]))
        raise HTTPException(
            status_code=400,
            detail=f"{kind} 文件格式不支持：{file.filename}，允许：{allowed}",
        )

    target_path = target_dir / (file.filename or f"{kind}{suffix}")
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return target_path


def extract_zip_if_needed(file_path: Path) -> Path:
    if file_path.suffix.lower() != ".zip":
        return file_path.parent

    extract_dir = file_path.parent / file_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(file_path, "r") as zf:
        zf.extractall(extract_dir)
    return extract_dir


def read_table_file(file_path: Path, sheet_name: str | int | None = 0, header: int | None = 0) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path, header=header)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path, sheet_name=sheet_name, header=header)
    raise ValueError(f"暂不支持的表格文件格式：{file_path.name}")


def normalize_column_name(name: object) -> str:
    text = str(name).strip()
    text = text.replace("\n", " ").replace("\r", " ")
    return text