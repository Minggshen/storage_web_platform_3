from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from models.api_models import RunRequest
from services.file_store import EXPORT_DIR

VALIDATIONS: Dict[str, Dict[str, Any]] = {}
TASKS: Dict[str, Dict[str, Any]] = {}
STATE_LOCK = threading.Lock()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def register_validation(payload: Dict[str, Any]) -> str:
    validation_id = new_id("val")
    with STATE_LOCK:
        VALIDATIONS[validation_id] = payload
    return validation_id


def get_validation(validation_id: str) -> Dict[str, Any]:
    with STATE_LOCK:
        payload = VALIDATIONS.get(validation_id)
    if payload is None:
        raise KeyError(f"未找到 validation_id={validation_id}")
    return payload


@dataclass
class TaskUpdater:
    task_id: str

    def log(self, message: str) -> None:
        with STATE_LOCK:
            TASKS[self.task_id]["logs"].append(message)
            TASKS[self.task_id]["updated_at"] = time.time()

    def progress(self, value: int) -> None:
        with STATE_LOCK:
            TASKS[self.task_id]["progress"] = max(0, min(100, int(value)))
            TASKS[self.task_id]["updated_at"] = time.time()

    def status(self, value: str) -> None:
        with STATE_LOCK:
            TASKS[self.task_id]["status"] = value
            TASKS[self.task_id]["updated_at"] = time.time()

    def fail(self, message: str) -> None:
        with STATE_LOCK:
            TASKS[self.task_id]["status"] = "failed"
            TASKS[self.task_id]["error"] = message
            TASKS[self.task_id]["updated_at"] = time.time()
            TASKS[self.task_id]["logs"].append(f"[失败] {message}")

    def finish(self, result: Dict[str, Any]) -> None:
        with STATE_LOCK:
            TASKS[self.task_id]["status"] = "completed"
            TASKS[self.task_id]["progress"] = 100
            TASKS[self.task_id]["updated_at"] = time.time()
            TASKS[self.task_id]["finished_at"] = time.time()
            TASKS[self.task_id]["result"] = result
            TASKS[self.task_id]["logs"].append("[完成] 任务执行结束，结果已可读取。")


def create_task(config: RunRequest) -> str:
    task_id = new_id("task")
    now = time.time()
    with STATE_LOCK:
        TASKS[task_id] = {
            "task_id": task_id,
            "validation_id": config.validation_id,
            "project_name": config.project_name,
            "scene_name": config.scene_name,
            "optimizer": config.optimizer,
            "dispatch_mode": config.dispatch_mode,
            "status": "queued",
            "progress": 0,
            "started_at": now,
            "finished_at": None,
            "updated_at": now,
            "logs": ["[创建] 已创建任务。"],
            "error": None,
            "result": None,
        }
    return task_id


def get_task(task_id: str) -> Dict[str, Any]:
    with STATE_LOCK:
        task = TASKS.get(task_id)
    if task is None:
        raise KeyError(f"未找到 task_id={task_id}")
    return task


def build_mock_result(task_id: str) -> Dict[str, Any]:
    export_dir = EXPORT_DIR / task_id
    export_dir.mkdir(parents=True, exist_ok=True)

    summary_path = export_dir / "summary.json"
    result_path = export_dir / "result.json"

    result = {
        "summary": {
            "optimal_power_kw": 1250,
            "optimal_energy_kwh": 2500,
            "duration_h": 2.0,
            "annual_equivalent_cycles": 428,
            "annual_net_revenue_wan_yuan": 31.8,
            "lifecycle_npv_wan_yuan": 168.4,
            "payback_years": 5.2,
            "voltage_improvement_pct": 2.7,
        },
        "charts": {
            "daily_dispatch_data": [
                {"hour": "00", "soc": 48, "charge": 280, "discharge": 0, "price": 0.41, "load": 1320},
                {"hour": "04", "soc": 74, "charge": 420, "discharge": 0, "price": 0.37, "load": 1160},
                {"hour": "08", "soc": 68, "charge": 0, "discharge": 160, "price": 0.63, "load": 1540},
                {"hour": "12", "soc": 52, "charge": 0, "discharge": 420, "price": 0.91, "load": 1830},
                {"hour": "16", "soc": 29, "charge": 0, "discharge": 610, "price": 1.07, "load": 2140},
                {"hour": "20", "soc": 25, "charge": 0, "discharge": 120, "price": 0.75, "load": 1910},
                {"hour": "23", "soc": 48, "charge": 260, "discharge": 0, "price": 0.47, "load": 1440},
            ],
            "annual_economics_data": [
                {"item": "峰谷套利收益", "value": 92},
                {"item": "需量管理收益", "value": 46},
                {"item": "辅助服务收益", "value": 31},
                {"item": "电压越限惩罚", "value": -6},
                {"item": "运维成本", "value": -15},
                {"item": "衰减成本", "value": -13},
                {"item": "替换储备金", "value": -9},
            ],
            "voltage_envelope_data": [
                {"month": "1月", "baseline": 0.921, "storage": 0.948},
                {"month": "2月", "baseline": 0.928, "storage": 0.953},
                {"month": "3月", "baseline": 0.934, "storage": 0.958},
                {"month": "4月", "baseline": 0.939, "storage": 0.962},
                {"month": "5月", "baseline": 0.931, "storage": 0.957},
                {"month": "6月", "baseline": 0.924, "storage": 0.951},
                {"month": "7月", "baseline": 0.918, "storage": 0.946},
                {"month": "8月", "baseline": 0.916, "storage": 0.944},
                {"month": "9月", "baseline": 0.927, "storage": 0.952},
                {"month": "10月", "baseline": 0.936, "storage": 0.960},
                {"month": "11月", "baseline": 0.941, "storage": 0.964},
                {"month": "12月", "baseline": 0.933, "storage": 0.957},
            ],
        },
        "candidate_schemes": [
            {
                "name": "常规设备方案",
                "power_kw": 1250,
                "energy_kwh": 2500,
                "duration_h": 2.0,
                "npv_wan_yuan": 168.4,
                "payback_years": 5.2,
                "voltage_improvement_pct": 2.7,
                "safety_level": "标准",
            },
            {
                "name": "高安全设备方案",
                "power_kw": 1100,
                "energy_kwh": 2420,
                "duration_h": 2.2,
                "npv_wan_yuan": 153.1,
                "payback_years": 5.9,
                "voltage_improvement_pct": 3.2,
                "safety_level": "高",
            },
            {
                "name": "经济优先方案",
                "power_kw": 1500,
                "energy_kwh": 3000,
                "duration_h": 2.0,
                "npv_wan_yuan": 181.9,
                "payback_years": 4.9,
                "voltage_improvement_pct": 2.1,
                "safety_level": "中",
            },
        ],
        "device_mapping": [
            {"type": "电池簇", "vendor": "设备策略库读取", "model": "LFP-280Ah / 示例", "qty": "8 簇", "remark": "来自设备策略库"},
            {"type": "PCS", "vendor": "设备策略库读取", "model": "1250kW 双向变流器", "qty": "1 台", "remark": "按功率向上匹配"},
            {"type": "BMS/EMS", "vendor": "设备策略库读取", "model": "标准配置", "qty": "1 套", "remark": "支持经济/高安全策略切换"},
            {"type": "消防与热管理", "vendor": "设备策略库读取", "model": "Pack 级/舱级", "qty": "1 套", "remark": "高安全方案权重更高"},
        ],
        "exports": {
            "summary_file": str(summary_path),
            "result_file": str(result_path),
        },
    }

    summary_path.write_text(json.dumps(result["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result