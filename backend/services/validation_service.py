from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from models.api_models import ValidationCheck, ValidationSummary
from services.registry_service import validate_registry
from services.runtime_service import validate_runtime_files
from services.strategy_service import validate_strategy_library
from services.tariff_service import validate_tariff
from services.task_service import register_validation


def validate_all_inputs(
    scene_name: str,
    strict_tariff: bool,
    registry_path: Optional[Path],
    tariff_path: Optional[Path],
    runtime_year_map_path: Optional[Path],
    runtime_model_library_path: Optional[Path],
    storage_path: Optional[Path],
    dss_path: Optional[Path],
    saved_dir: Path,
) -> ValidationSummary:
    checks = []
    warnings = []
    summaries: Dict[str, Any] = {}

    checks.append(
        {
            "name": "场景名称",
            "ok": bool(scene_name.strip()),
            "detail": "场景名称已提供" if scene_name.strip() else "场景名称为空",
        }
    )

    files = {
        "registry": str(registry_path) if registry_path else None,
        "tariff": str(tariff_path) if tariff_path else None,
        "runtime_year_map": str(runtime_year_map_path) if runtime_year_map_path else None,
        "runtime_model_library": str(runtime_model_library_path) if runtime_model_library_path else None,
        "storage": str(storage_path) if storage_path else None,
        "dss": str(dss_path) if dss_path else None,
    }

    if registry_path is not None:
        sub_checks, sub_summary = validate_registry(registry_path)
        checks.extend(sub_checks)
        summaries["registry"] = sub_summary
    else:
        checks.append({"name": "节点注册表上传", "ok": False, "detail": "未上传节点注册表"})

    sub_checks, sub_summary = validate_runtime_files(
        year_map_path=runtime_year_map_path,
        model_library_path=runtime_model_library_path,
    )
    checks.extend(sub_checks)
    summaries["runtime"] = sub_summary

    if tariff_path is not None:
        sub_checks, sub_summary = validate_tariff(tariff_path, strict_tariff=strict_tariff)
        checks.extend(sub_checks)
        summaries["tariff"] = sub_summary
    else:
        checks.append({"name": "年度电价表上传", "ok": False, "detail": "未上传年度电价表"})

    if storage_path is not None:
        sub_checks, sub_summary = validate_strategy_library(storage_path)
        checks.extend(sub_checks)
        summaries["strategy"] = sub_summary
    else:
        checks.append({"name": "储能设备策略库上传", "ok": False, "detail": "未上传储能设备策略库"})

    if dss_path is None:
        warnings.append("当前未上传 OpenDSS 文件；第一批真实校验层允许为空，后续接真实运行时再补充。")
        checks.append({"name": "OpenDSS 文件上传", "ok": True, "detail": "当前版本允许为空"})
    else:
        checks.append({"name": "OpenDSS 文件上传", "ok": True, "detail": f"已接收 {Path(dss_path).name}"})

    ok = all(item["ok"] for item in checks)

    payload = {
        "scene_name": scene_name,
        "saved_dir": str(saved_dir),
        "files": files,
        "checks": checks,
        "warnings": warnings,
        "summaries": summaries,
        "ok": ok,
    }
    validation_id = register_validation(payload)

    return ValidationSummary(
        ok=ok,
        validation_id=validation_id,
        scene_name=scene_name,
        saved_dir=str(saved_dir),
        files=files,
        checks=[ValidationCheck(**item) for item in checks],
        warnings=warnings,
        summaries=summaries,
    )