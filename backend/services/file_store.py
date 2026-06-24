from __future__ import annotations

import os
import shutil
import stat
import uuid
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
    "registry": {".xlsx", ".xlsm", ".csv"},
    "tariff": {".xlsx", ".xlsm", ".csv"},
    "storage": {".xlsx", ".xlsm"},
    "runtime": {".xlsx", ".xlsm", ".csv", ".zip"},
    "dss": {".dss", ".txt", ".zip"},
}

MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024


async def save_upload(file: Optional[UploadFile], target_dir: Path, kind: str) -> Optional[Path]:
    if file is None:
        return None

    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES[kind]:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES[kind]))
        raise HTTPException(
            status_code=400,
            detail=f"{kind} 文件格式不支持：{file.filename}，允许：{allowed}",
        )

    safe_name = Path(file.filename).name if file.filename else f"{kind}{suffix}"
    target_path = target_dir / safe_name
    temp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            buffer.flush()
            os.fsync(buffer.fileno())
        os.replace(temp_path, target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return target_path


def extract_zip_if_needed(file_path: Path) -> Path:
    if file_path.suffix.lower() != ".zip":
        return file_path.parent

    extract_dir = file_path.parent / file_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(file_path, "r") as zf:
        _safe_extract_zip(zf, extract_dir)
    return extract_dir


def _safe_extract_zip(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    base_dir = extract_dir.resolve()
    members = zf.infolist()
    if len(members) > MAX_ZIP_ENTRIES:
        raise HTTPException(status_code=400, detail=f"压缩包文件数量过多：{len(members)} > {MAX_ZIP_ENTRIES}")

    total_uncompressed_size = 0
    for member in members:
        member_path = Path(member.filename)
        target_path = (base_dir / member.filename).resolve()
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise HTTPException(status_code=400, detail=f"压缩包包含不支持的符号链接：{member.filename}")
        if member_path.is_absolute() or not _is_path_within(target_path, base_dir):
            raise HTTPException(status_code=400, detail=f"压缩包路径越界：{member.filename}")
        if member.file_size > MAX_ZIP_MEMBER_UNCOMPRESSED_BYTES:
            raise HTTPException(status_code=400, detail=f"压缩包单文件解压后过大：{member.filename}")
        total_uncompressed_size += member.file_size
        if total_uncompressed_size > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
            raise HTTPException(status_code=400, detail="压缩包解压后总大小超过限制。")

    for member in members:
        zf.extract(member, base_dir)


def _is_path_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def read_table_file(file_path: Path, sheet_name: str | int | None = 0, header: int | None = 0) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path, header=header)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(file_path, sheet_name=sheet_name, header=header)
    raise ValueError(f"暂不支持的表格文件格式：{file_path.name}")


def normalize_column_name(name: object) -> str:
    text = str(name).strip()
    text = text.replace("\n", " ").replace("\r", " ")
    return text
