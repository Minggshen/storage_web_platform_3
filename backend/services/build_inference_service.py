
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.project_model import SearchSpaceInferenceRow
from services.project_model_service import ProjectModelService
from services.search_space_inference_service import SearchSpaceInferenceService


class BuildInferenceService:
    def __init__(
        self,
        project_service: Optional[ProjectModelService] = None,
        inference_service: Optional[SearchSpaceInferenceService] = None,
    ) -> None:
        self.project_service = project_service or ProjectModelService()
        self.inference_service = inference_service or SearchSpaceInferenceService()

    def get_inference_rows(self, project_id: str) -> List[SearchSpaceInferenceRow]:
        project = self.project_service.load_project(project_id)
        rows: List[SearchSpaceInferenceRow] = []
        records = project.device_library.records

        for node in project.network.nodes:
            if str(getattr(node.type, "value", node.type)) != "load":
                continue
            stats = self._load_runtime_stats(project, node)
            params = dict(node.params or {})
            for key in (
                "grid_interconnection_limit_kw",
                "device_power_max_kw",
                "search_power_min_kw",
                "search_duration_min_h",
                "search_duration_max_h",
            ):
                params.pop(key, None)
            transformer_capacity_kva = self._safe_float(params.get("transformer_capacity_kva"))
            transformer_pf_limit = self._safe_float(params.get("transformer_pf_limit"), 0.95)
            transformer_reserve_ratio = self._safe_float(params.get("transformer_reserve_ratio"), 0.15)
            grid_interconnection_limit_kw = None
            result = self.inference_service.infer(
                node_params=params,
                runtime_stats=stats,
                device_records=records,
                transformer_capacity_kva=transformer_capacity_kva,
                transformer_pf_limit=transformer_pf_limit,
                transformer_reserve_ratio=transformer_reserve_ratio,
                grid_interconnection_limit_kw=grid_interconnection_limit_kw,
            )
            rows.append(SearchSpaceInferenceRow(
                node_id=node.id,
                node_name=node.name,
                node_type=str(getattr(node.type, "value", node.type)),
                transformer_capacity_kva=transformer_capacity_kva,
                transformer_pf_limit=transformer_pf_limit,
                transformer_reserve_ratio=transformer_reserve_ratio,
                grid_interconnection_limit_kw=grid_interconnection_limit_kw,
                peak_kw=result.peak_kw,
                valley_kw=result.valley_kw,
                annual_mean_kw=result.annual_mean_kw,
                mean_daily_energy_kwh=result.mean_daily_energy_kwh,
                transformer_limit_kw=result.transformer_limit_kw,
                search_power_min_kw=result.search_power_min_kw,
                device_power_max_kw=result.device_power_max_kw,
                search_duration_min_h=result.search_duration_min_h,
                search_duration_max_h=result.search_duration_max_h,
                inference_source=result.source,
                basis=result.basis,
                notes=result.notes,
                explain=result.explain,
            ))
        return rows

    def _load_runtime_stats(self, project, node) -> Dict[str, Any]:
        if not node.runtime_binding:
            return {}
        year_asset = project.assets.get(node.runtime_binding.year_map_file_id or "")
        model_asset = project.assets.get(node.runtime_binding.model_library_file_id or "")
        if not year_asset or not model_asset:
            return {}

        year_path = Path(str(year_asset.metadata.get("stored_path", "")))
        model_path = Path(str(model_asset.metadata.get("stored_path", "")))
        if not year_path.exists() or not model_path.exists():
            return {}

        weights: Dict[str, int] = {}
        with year_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                model_id = str(row.get("internal_model_id") or "").strip()
                if model_id:
                    weights[model_id] = weights.get(model_id, 0) + 1

        peak_kw = None
        valley_kw = None
        weighted_mean = 0.0
        total_days = 0
        daily_energy_acc = 0.0
        with model_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                model_id = str(row.get("internal_model_id") or "").strip()
                w = weights.get(model_id, 0)
                if w <= 0:
                    continue
                vals = []
                for i in range(24):
                    for key in (f"h{i:02d}", f"H{i:02d}", f"load_{i:02d}", f"p_{i:02d}"):
                        if key in row:
                            try:
                                vals.append(float(row[key]))
                            except Exception:
                                vals.append(0.0)
                            break
                if not vals:
                    continue
                local_peak = max(vals)
                local_valley = min(vals)
                local_mean = sum(vals) / len(vals)
                local_daily_energy = sum(vals)
                peak_kw = local_peak if peak_kw is None else max(peak_kw, local_peak)
                valley_kw = local_valley if valley_kw is None else min(valley_kw, local_valley)
                weighted_mean += local_mean * w
                daily_energy_acc += local_daily_energy * w
                total_days += w

        annual_mean_kw = (weighted_mean / total_days) if total_days else None
        mean_daily_energy_kwh = (daily_energy_acc / total_days) if total_days else None
        return {
            "peak_kw": peak_kw,
            "valley_kw": valley_kw,
            "annual_mean_kw": annual_mean_kw,
            "mean_daily_energy_kwh": mean_daily_energy_kwh,
        }

    def _safe_float(self, value: Any, default: float | None = None) -> float | None:
        if value in (None, ""):
            return default
        try:
            return float(value)
        except Exception:
            return default
