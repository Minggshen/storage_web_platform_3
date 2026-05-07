
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from fastapi import UploadFile
from openpyxl import load_workbook

from models.project_model import (
    AssetRef,
    AssetValidationMessage,
    AssetValidationReport,
    DeviceRecord,
    ValidationStatus,
)
from services.project_model_service import ProjectModelService


@dataclass
class ParsedTable:
    headers: List[str]
    rows: List[Dict[str, Any]]


class AssetBindingService:
    def __init__(self, project_service: ProjectModelService | None = None) -> None:
        self.project_service = project_service or ProjectModelService()

    def upload_runtime_files(
        self,
        project_id: str,
        node_id: str,
        year_map_file: UploadFile,
        model_library_file: UploadFile,
    ) -> tuple[AssetRef, AssetValidationReport, AssetRef, AssetValidationReport, Any, Path]:
        self.project_service.ensure_load_node(project_id, node_id)

        year_map_asset, year_map_path, _, _ = self.project_service.save_asset_upload(
            project_id=project_id,
            upload_file=year_map_file,
            category="runtime",
            subfolder=node_id,
            metadata={"runtime_kind": "year_map", "node_id": node_id},
        )
        year_map_report = self.validate_runtime_year_map(year_map_path)
        year_map_asset.metadata["validation"] = year_map_report.model_dump(mode="json")

        model_asset, model_path, _, _ = self.project_service.save_asset_upload(
            project_id=project_id,
            upload_file=model_library_file,
            category="runtime",
            subfolder=node_id,
            metadata={"runtime_kind": "model_library", "node_id": node_id},
        )
        model_report = self.validate_runtime_model_library(model_path)
        model_asset.metadata["validation"] = model_report.model_dump(mode="json")

        project, project_file = self.project_service.bind_runtime_assets(
            project_id=project_id,
            node_id=node_id,
            year_map_asset=year_map_asset,
            model_library_asset=model_asset,
        )
        project.assets[year_map_asset.file_id] = year_map_asset
        project.assets[model_asset.file_id] = model_asset
        _, project_file = self.project_service.save_project(project)
        return year_map_asset, year_map_report, model_asset, model_report, project, project_file

    def upload_tariff_file(
        self,
        project_id: str,
        tariff_file: UploadFile,
    ) -> tuple[AssetRef, AssetValidationReport, Any, Path]:
        asset, target_path, _, _ = self.project_service.save_asset_upload(
            project_id=project_id,
            upload_file=tariff_file,
            category="tariff",
            metadata={"asset_kind": "tariff_annual"},
        )
        report = self.validate_tariff_file(target_path)
        asset.metadata["validation"] = report.model_dump(mode="json")
        detected_year = report.parsed_preview.get("detected_year")
        project, project_file = self.project_service.bind_tariff_asset(
            project_id=project_id,
            asset=asset,
            tariff_year=int(detected_year) if detected_year is not None else None,
        )
        project.assets[asset.file_id] = asset
        _, project_file = self.project_service.save_project(project)
        return asset, report, project, project_file

    def upload_device_library_file(
        self,
        project_id: str,
        device_file: UploadFile,
    ) -> tuple[AssetRef, AssetValidationReport, List[DeviceRecord], Any, Path]:
        asset, target_path, _, _ = self.project_service.save_asset_upload(
            project_id=project_id,
            upload_file=device_file,
            category="device_library",
            metadata={"asset_kind": "device_library"},
        )
        report, records = self.validate_device_library_file(target_path)
        asset.metadata["validation"] = report.model_dump(mode="json")
        project, project_file = self.project_service.replace_device_library(
            project_id=project_id,
            asset=asset,
            records=records,
        )
        project.assets[asset.file_id] = asset
        _, project_file = self.project_service.save_project(project)
        return asset, report, records, project, project_file

    def validate_runtime_year_map(self, file_path: str | Path) -> AssetValidationReport:
        table = self._read_table(file_path)
        report = self._new_report("runtime_year_map")
        header_map = self._normalize_header_map(table.headers)
        required = ["date", "internal_model_id"]
        missing = [field for field in required if field not in header_map]
        if missing:
            for field in missing:
                self._push_message(report, ValidationStatus.ERROR, "字段完整性", f"缺少字段：{field}")
            self._finalize_report(report)
            return report
        self._push_message(report, ValidationStatus.PASS, "字段完整性", "核心字段齐全")

        dates: List[date] = []
        model_ids: List[str] = []
        for idx, row in enumerate(table.rows, start=2):
            dt = self._parse_date(row.get(header_map["date"]))
            if dt is None:
                self._push_message(report, ValidationStatus.ERROR, "日期解析", "存在无法解析的日期", detail=f"第 {idx} 行")
            else:
                dates.append(dt)
            model_id = str(row.get(header_map["internal_model_id"], "")).strip()
            if not model_id:
                self._push_message(report, ValidationStatus.ERROR, "模型ID", "存在空 internal_model_id", detail=f"第 {idx} 行")
            else:
                model_ids.append(model_id)

        if len(table.rows) == 365:
            self._push_message(report, ValidationStatus.PASS, "天数检查", "当前 365 天")
        else:
            level = ValidationStatus.WARNING if len(table.rows) > 0 else ValidationStatus.ERROR
            self._push_message(report, level, "天数检查", f"当前 {len(table.rows)} 天，建议为 365 天")

        if dates:
            if len(set(dates)) == len(dates):
                self._push_message(report, ValidationStatus.PASS, "日期去重", "日期无重复")
            else:
                self._push_message(report, ValidationStatus.ERROR, "日期去重", "存在重复日期")
            if self._is_contiguous(sorted(dates)):
                self._push_message(report, ValidationStatus.PASS, "日期连续", "日期按天连续")
            else:
                self._push_message(report, ValidationStatus.WARNING, "日期连续", "日期未完全连续")

        report.parsed_preview = {
            "row_count": len(table.rows),
            "sample_model_ids": model_ids[:5],
            "date_start": dates[0].isoformat() if dates else None,
            "date_end": dates[-1].isoformat() if dates else None,
        }
        self._finalize_report(report)
        return report

    def validate_runtime_model_library(self, file_path: str | Path) -> AssetValidationReport:
        table = self._read_table(file_path)
        report = self._new_report("runtime_model_library")
        header_map = self._normalize_header_map(table.headers)
        required = ["internal_model_id", *[f"h{i:02d}" for i in range(24)]]
        missing = [field for field in required if field not in header_map]
        if missing:
            for field in missing:
                self._push_message(report, ValidationStatus.ERROR, "字段完整性", f"缺少字段：{field}")
            self._finalize_report(report)
            return report
        self._push_message(report, ValidationStatus.PASS, "字段完整性", "模型库字段齐全")

        model_ids: List[str] = []
        for idx, row in enumerate(table.rows, start=2):
            model_id = str(row.get(header_map["internal_model_id"], "")).strip()
            if not model_id:
                self._push_message(report, ValidationStatus.ERROR, "模型ID", "存在空 internal_model_id", detail=f"第 {idx} 行")
            model_ids.append(model_id)
            for hour_key in [f"h{i:02d}" for i in range(24)]:
                value = row.get(header_map[hour_key])
                if self._coerce_float(value) is None:
                    self._push_message(report, ValidationStatus.ERROR, "24点曲线", f"{hour_key} 无法解析为数值", detail=f"第 {idx} 行")
                    break

        if len(set(filter(None, model_ids))) == len(list(filter(None, model_ids))):
            self._push_message(report, ValidationStatus.PASS, "模型ID唯一性", "模型 ID 无重复")
        else:
            self._push_message(report, ValidationStatus.ERROR, "模型ID唯一性", "存在重复的 internal_model_id")

        report.parsed_preview = {"row_count": len(table.rows), "sample_model_ids": model_ids[:5]}
        self._finalize_report(report)
        return report

    def validate_tariff_file(self, file_path: str | Path) -> AssetValidationReport:
        table = self._read_table(file_path)
        report = self._new_report("tariff_annual")
        header_map = self._normalize_header_map(table.headers)
        required = ["date", *[f"电价_{i:02d}" for i in range(24)]]
        missing = [field for field in required if field not in header_map]
        if missing:
            for field in missing:
                self._push_message(report, ValidationStatus.ERROR, "字段完整性", f"缺少字段：{field}")
            self._finalize_report(report)
            return report
        self._push_message(report, ValidationStatus.PASS, "字段完整性", "电价表字段完整")

        dates: List[date] = []
        detected_year: Optional[int] = None
        for idx, row in enumerate(table.rows, start=2):
            dt = self._parse_date(row.get(header_map["date"]))
            if dt is None:
                self._push_message(report, ValidationStatus.ERROR, "日期解析", "存在无法解析的日期", detail=f"第 {idx} 行")
            else:
                dates.append(dt)
                if detected_year is None:
                    detected_year = dt.year
            for hour_key in [f"电价_{i:02d}" for i in range(24)]:
                value = self._coerce_float(row.get(header_map[hour_key]))
                if value is None:
                    self._push_message(report, ValidationStatus.ERROR, "电价值解析", f"{hour_key} 无法解析为数值", detail=f"第 {idx} 行")
                    break

        if len(table.rows) == 365:
            self._push_message(report, ValidationStatus.PASS, "天数检查", "当前 365 天")
        else:
            level = ValidationStatus.WARNING if len(table.rows) > 0 else ValidationStatus.ERROR
            self._push_message(report, level, "天数检查", f"当前 {len(table.rows)} 天，建议为 365 天")

        if dates:
            if len(set(dates)) == len(dates):
                self._push_message(report, ValidationStatus.PASS, "日期去重", "日期无重复")
            else:
                self._push_message(report, ValidationStatus.ERROR, "日期去重", "存在重复日期")
            if self._is_contiguous(sorted(dates)):
                self._push_message(report, ValidationStatus.PASS, "日期连续", "日期逐天连续")
            else:
                self._push_message(report, ValidationStatus.WARNING, "日期连续", "日期未完全连续")

        report.parsed_preview = {
            "row_count": len(table.rows),
            "detected_year": detected_year,
            "date_start": dates[0].isoformat() if dates else None,
            "date_end": dates[-1].isoformat() if dates else None,
        }
        self._finalize_report(report)
        return report

    def validate_device_library_file(self, file_path: str | Path) -> tuple[AssetValidationReport, List[DeviceRecord]]:
        table = self._read_table(file_path)
        report = self._new_report("device_library")
        header_map = self._normalize_header_map(table.headers)
        required = ["vendor", "model"]
        missing = [field for field in required if field not in header_map]
        if missing:
            for field in missing:
                self._push_message(report, ValidationStatus.ERROR, "字段完整性", f"缺少字段：{field}")
            self._finalize_report(report)
            return report, []
        self._push_message(report, ValidationStatus.PASS, "字段完整性", "设备主字段完整")

        records: List[DeviceRecord] = []
        enabled_count = 0
        for idx, row in enumerate(table.rows, start=2):
            vendor = str(row.get(header_map["vendor"], "")).strip()
            model = str(row.get(header_map["model"], "")).strip()
            if not vendor or not model:
                self._push_message(report, ValidationStatus.ERROR, "记录合法性", "存在空厂家或型号", detail=f"第 {idx} 行")
                continue

            duration = self._value_by_alias(row, header_map, ["duration_hour", "duration_h", "时长_h", "时长"])
            rated_power = self._value_by_alias(row, header_map, ["rated_power_kw", "额定功率_kw", "功率_kw"])
            rated_energy = self._value_by_alias(row, header_map, ["rated_energy_kwh", "额定容量_kwh", "容量_kwh"])
            if duration is None and rated_power and rated_energy and rated_power > 0:
                duration = round(rated_energy / rated_power, 4)

            energy_unit_price = self._value_by_alias(
                row, header_map,
                ["energy_unit_price_yuan_per_kwh", "energy_unit_price", "价格_元每kwh", "energy_price_yuan_per_kwh"]
            )
            price_yuan_per_wh = self._value_by_alias(
                row, header_map, ["price_yuan_per_wh", "价格_元每wh", "价格元每wh"]
            )
            if price_yuan_per_wh is None and energy_unit_price is not None:
                price_yuan_per_wh = round(float(energy_unit_price) / 1000.0, 6)

            safety_level = self._string_by_alias(row, header_map, ["safety_level", "manual_safety_grade", "安全等级", "manual_safety_grade"])
            ems_package = self._string_by_alias(row, header_map, ["ems_package", "ems_package_name", "ems包", "ems_package_name"])

            core_keys = {
                "enabled","vendor","series_name","model","device_family","system_topology_type","application_scene",
                "cni_fit_level","is_default_candidate","ems_package_name","has_builtin_ems","requires_external_pcs",
                "supports_black_start","supports_offgrid_microgrid","battery_chemistry","rated_power_kw","rated_energy_kwh",
                "usable_energy_kwh_at_fat","duration_h","duration_hour","dc_voltage_range_v","ac_grid_voltage_v","battery_config",
                "cooling_type","fire_detection","fire_suppression","backup_system","accident_ventilation",
                "pack_level_firefighting_optional","explosion_relief_optional","msd_required","communication_protocol",
                "manual_safety_grade","manual_safety_notes","efficiency_pct","ip_system","corrosion_grade","install_mode",
                "aux_power_interface","dimension_w_mm","dimension_d_mm","dimension_h_mm","weight_kg","price_yuan_per_wh",
                "energy_unit_price_yuan_per_kwh","power_related_capex_yuan_per_kw","station_integration_capex_ratio",
                "fire_protection_capex_ratio","annual_insurance_rate_on_capex","annual_safety_maintenance_rate_on_capex",
                "annual_fire_system_inspection_rate_on_capex","price_status","quote_source","source_files",
                "cycle_life","soc_min","soc_max","safety_level","ems_package"
            }
            extra: Dict[str, Any] = {}
            for norm_key, original in header_map.items():
                if norm_key in core_keys:
                    continue
                extra[norm_key] = row.get(original)

            record = DeviceRecord(
                enabled=self._bool_by_alias(row, header_map, ["enabled", "启用"], default=True),
                vendor=vendor,
                model=model,
                series_name=self._string_by_alias(row, header_map, ["series_name"]),
                device_family=self._string_by_alias(row, header_map, ["device_family"]),
                system_topology_type=self._string_by_alias(row, header_map, ["system_topology_type"]),
                application_scene=self._string_by_alias(row, header_map, ["application_scene"]),
                cni_fit_level=self._string_by_alias(row, header_map, ["cni_fit_level"]),
                is_default_candidate=self._bool_by_alias(row, header_map, ["is_default_candidate"], default=False) if "is_default_candidate" in header_map else None,
                ems_package=ems_package,
                ems_package_name=self._string_by_alias(row, header_map, ["ems_package_name"]),
                has_builtin_ems=self._bool_by_alias(row, header_map, ["has_builtin_ems"], default=False) if "has_builtin_ems" in header_map else None,
                requires_external_pcs=self._bool_by_alias(row, header_map, ["requires_external_pcs"], default=False) if "requires_external_pcs" in header_map else None,
                supports_black_start=self._bool_by_alias(row, header_map, ["supports_black_start"], default=False) if "supports_black_start" in header_map else None,
                supports_offgrid_microgrid=self._bool_by_alias(row, header_map, ["supports_offgrid_microgrid"], default=False) if "supports_offgrid_microgrid" in header_map else None,
                battery_chemistry=self._string_by_alias(row, header_map, ["battery_chemistry"]),
                rated_power_kw=rated_power,
                rated_energy_kwh=rated_energy,
                usable_energy_kwh_at_fat=self._value_by_alias(row, header_map, ["usable_energy_kwh_at_fat"]),
                duration_hour=duration,
                dc_voltage_range_v=self._string_by_alias(row, header_map, ["dc_voltage_range_v"]),
                ac_grid_voltage_v=self._string_by_alias(row, header_map, ["ac_grid_voltage_v"]),
                battery_config=self._string_by_alias(row, header_map, ["battery_config"]),
                cooling_type=self._string_by_alias(row, header_map, ["cooling_type"]),
                fire_detection=self._string_by_alias(row, header_map, ["fire_detection"]),
                fire_suppression=self._string_by_alias(row, header_map, ["fire_suppression"]),
                backup_system=self._string_by_alias(row, header_map, ["backup_system"]),
                accident_ventilation=self._bool_by_alias(row, header_map, ["accident_ventilation"], default=False) if "accident_ventilation" in header_map else None,
                pack_level_firefighting_optional=self._bool_by_alias(row, header_map, ["pack_level_firefighting_optional"], default=False) if "pack_level_firefighting_optional" in header_map else None,
                explosion_relief_optional=self._bool_by_alias(row, header_map, ["explosion_relief_optional"], default=False) if "explosion_relief_optional" in header_map else None,
                msd_required=self._bool_by_alias(row, header_map, ["msd_required"], default=False) if "msd_required" in header_map else None,
                communication_protocol=self._string_by_alias(row, header_map, ["communication_protocol"]),
                safety_level=safety_level,
                manual_safety_grade=self._string_by_alias(row, header_map, ["manual_safety_grade"]),
                manual_safety_notes=self._string_by_alias(row, header_map, ["manual_safety_notes"]),
                cycle_life=self._int_by_alias(row, header_map, ["cycle_life", "循环寿命"]),
                soc_min=self._value_by_alias(row, header_map, ["soc_min", "soc下限"]),
                soc_max=self._value_by_alias(row, header_map, ["soc_max", "soc上限"]),
                efficiency_pct=self._value_by_alias(row, header_map, ["efficiency_pct"]),
                ip_system=self._string_by_alias(row, header_map, ["ip_system"]),
                corrosion_grade=self._string_by_alias(row, header_map, ["corrosion_grade"]),
                install_mode=self._string_by_alias(row, header_map, ["install_mode"]),
                aux_power_interface=self._string_by_alias(row, header_map, ["aux_power_interface"]),
                dimension_w_mm=self._value_by_alias(row, header_map, ["dimension_w_mm"]),
                dimension_d_mm=self._value_by_alias(row, header_map, ["dimension_d_mm"]),
                dimension_h_mm=self._value_by_alias(row, header_map, ["dimension_h_mm"]),
                weight_kg=self._value_by_alias(row, header_map, ["weight_kg"]),
                price_yuan_per_wh=price_yuan_per_wh,
                energy_unit_price_yuan_per_kwh=energy_unit_price,
                power_related_capex_yuan_per_kw=self._value_by_alias(row, header_map, ["power_related_capex_yuan_per_kw"]),
                station_integration_capex_ratio=self._value_by_alias(row, header_map, ["station_integration_capex_ratio"]),
                fire_protection_capex_ratio=self._value_by_alias(row, header_map, ["fire_protection_capex_ratio"]),
                annual_insurance_rate_on_capex=self._value_by_alias(row, header_map, ["annual_insurance_rate_on_capex"]),
                annual_safety_maintenance_rate_on_capex=self._value_by_alias(row, header_map, ["annual_safety_maintenance_rate_on_capex"]),
                annual_fire_system_inspection_rate_on_capex=self._value_by_alias(row, header_map, ["annual_fire_system_inspection_rate_on_capex"]),
                price_status=self._string_by_alias(row, header_map, ["price_status"]),
                quote_source=self._string_by_alias(row, header_map, ["quote_source"]),
                source_files=self._string_by_alias(row, header_map, ["source_files"]),
                extra=extra,
            )
            record = self._complete_device_record(record)
            if record.enabled:
                enabled_count += 1
            records.append(record)

        if records:
            self._push_message(report, ValidationStatus.PASS, "记录数量", f"当前导入 {len(records)} 条设备记录")
        else:
            self._push_message(report, ValidationStatus.ERROR, "记录数量", "未导入到任何设备记录")

        if enabled_count > 0:
            self._push_message(report, ValidationStatus.PASS, "启用记录", f"当前启用设备数：{enabled_count}")
        else:
            self._push_message(report, ValidationStatus.WARNING, "启用记录", "当前没有启用设备")

        enabled_missing_price = sum(1 for r in records if r.enabled and r.energy_unit_price_yuan_per_kwh is None and r.price_yuan_per_wh is None)
        if enabled_missing_price:
            self._push_message(report, ValidationStatus.WARNING, "价格字段", f"存在 {enabled_missing_price} 条启用设备未填写价格字段")
        report.parsed_preview = {
            "record_count": len(records),
            "enabled_count": enabled_count,
            "sample_records": [f"{item.vendor}/{item.model}" for item in records[:5]],
        }
        self._finalize_report(report)
        return report, records


    def _complete_device_record(self, record: DeviceRecord) -> DeviceRecord:
        """Fill conservative defaults so the generated engineering model is closer to the original optimization inputs."""
        if record.usable_energy_kwh_at_fat is None and record.rated_energy_kwh is not None:
            record.usable_energy_kwh_at_fat = record.rated_energy_kwh

        if record.price_yuan_per_wh is None and record.energy_unit_price_yuan_per_kwh is not None:
            record.price_yuan_per_wh = round(float(record.energy_unit_price_yuan_per_kwh) / 1000.0, 6)
        if record.energy_unit_price_yuan_per_kwh is None and record.price_yuan_per_wh is not None:
            record.energy_unit_price_yuan_per_kwh = round(float(record.price_yuan_per_wh) * 1000.0, 3)

        if record.duration_hour is None and record.rated_power_kw not in (None, 0) and record.rated_energy_kwh is not None:
            record.duration_hour = round(float(record.rated_energy_kwh) / float(record.rated_power_kw), 4)
        if record.rated_power_kw is None and record.rated_energy_kwh is not None and record.duration_hour not in (None, 0):
            record.rated_power_kw = round(float(record.rated_energy_kwh) / float(record.duration_hour), 4)
        if record.rated_energy_kwh is None and record.rated_power_kw is not None and record.duration_hour not in (None, 0):
            record.rated_energy_kwh = round(float(record.rated_power_kw) * float(record.duration_hour), 4)

        # Conservative topology-based fallback when only energy is known.
        if record.rated_power_kw is None and record.rated_energy_kwh is not None:
            inferred_duration = self._infer_default_duration(record)
            if inferred_duration is not None and inferred_duration > 0:
                record.duration_hour = record.duration_hour or inferred_duration
                record.rated_power_kw = round(float(record.rated_energy_kwh) / inferred_duration, 4)
                record.extra["inferred_rated_power_kw"] = True
                record.extra["inference_basis"] = f"duration={inferred_duration}h"

        if record.rated_energy_kwh is None and record.rated_power_kw is not None:
            inferred_duration = self._infer_default_duration(record)
            if inferred_duration is not None and inferred_duration > 0:
                record.duration_hour = record.duration_hour or inferred_duration
                record.rated_energy_kwh = round(float(record.rated_power_kw) * inferred_duration, 4)
                record.extra["inferred_rated_energy_kwh"] = True
                record.extra["inference_basis"] = f"duration={inferred_duration}h"

        if record.cycle_life is None and record.enabled:
            record.cycle_life = self._infer_default_cycle_life(record)
            record.extra["default_cycle_life_applied"] = True
        if record.soc_min is None and record.enabled and record.system_topology_type != "dc_dc_coupled_unit":
            record.soc_min = 0.10
            record.extra["default_soc_min_applied"] = True
        if record.soc_max is None and record.enabled and record.system_topology_type != "dc_dc_coupled_unit":
            record.soc_max = 0.90
            record.extra["default_soc_max_applied"] = True
        if record.efficiency_pct is None and record.enabled:
            record.efficiency_pct = self._infer_default_efficiency(record)
            record.extra["default_efficiency_pct_applied"] = True
        return record

    def _infer_default_duration(self, record: DeviceRecord) -> Optional[float]:
        topology = (record.system_topology_type or "").strip().lower()
        family = (record.device_family or "").strip().lower()
        model = (record.model or "").strip().lower()
        if "4h" in model:
            return 4.0
        if "2h" in model or "233kwh" in model:
            return 2.0
        if topology in {"ac_all_in_one", "outdoor_liquid_cooled_cabinet"}:
            return 2.0
        if topology in {"containerized_large_scale", "dc_side_battery_cabinet"}:
            return 4.0 if (record.rated_energy_kwh or 0) >= 4000 else 2.0
        if "一体机" in family or "柜式" in family:
            return 2.0
        return None

    def _infer_default_cycle_life(self, record: DeviceRecord) -> int:
        chemistry = (record.battery_chemistry or "").strip().upper()
        topology = (record.system_topology_type or "").strip().lower()
        if "LFP" in chemistry and topology in {"containerized_large_scale", "dc_side_battery_cabinet"}:
            return 10000
        if "LFP" in chemistry:
            return 8000
        return 6000

    def _infer_default_efficiency(self, record: DeviceRecord) -> Optional[float]:
        topology = (record.system_topology_type or "").strip().lower()
        if topology in {"ac_all_in_one", "outdoor_liquid_cooled_cabinet"}:
            return 88.0
        if topology in {"containerized_large_scale", "dc_side_battery_cabinet"}:
            return 90.0
        if topology == "dc_dc_coupled_unit":
            return 99.0
        return None

    def _new_report(self, asset_kind: str) -> AssetValidationReport:
        return AssetValidationReport(ok=False, asset_kind=asset_kind)

    def _push_message(self, report: AssetValidationReport, status: ValidationStatus, title: str, message: str, detail: str | None = None) -> None:
        report.messages.append(AssetValidationMessage(status=status, title=title, message=message, detail=detail))

    def _finalize_report(self, report: AssetValidationReport) -> None:
        report.pass_count = sum(1 for item in report.messages if item.status == ValidationStatus.PASS)
        report.warning_count = sum(1 for item in report.messages if item.status == ValidationStatus.WARNING)
        report.error_count = sum(1 for item in report.messages if item.status == ValidationStatus.ERROR)
        report.ok = report.error_count == 0

    def _read_table(self, file_path: str | Path) -> ParsedTable:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return self._read_csv(path)
        if suffix in {".xlsx", ".xlsm"}:
            return self._read_xlsx(path)
        raise ValueError(f"暂不支持的文件格式：{path.suffix}")

    def _read_csv(self, path: Path) -> ParsedTable:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            rows = [dict(row) for row in reader]
        return ParsedTable(headers=headers, rows=rows)

    def _read_xlsx(self, path: Path) -> ParsedTable:
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        headers = [str(cell).strip() if cell is not None else "" for cell in header_row]
        rows: List[Dict[str, Any]] = []
        for values in ws.iter_rows(min_row=2, values_only=True):
            if values is None:
                continue
            row = {headers[idx]: values[idx] if idx < len(values) else None for idx in range(len(headers))}
            if any(v not in (None, "") for v in row.values()):
                rows.append(row)
        return ParsedTable(headers=headers, rows=rows)

    def _normalize_header_map(self, headers: Sequence[str]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for original in headers:
            key = self._normalize_header_name(original)
            if key:
                mapping[key] = original
        return mapping

    def _normalize_header_name(self, header: Any) -> str:
        text = str(header or "").strip().lower()
        alias_map = {
            "日期": "date",
            "date": "date",
            "day": "date",
            "internal_model_id": "internal_model_id",
            "model_id": "internal_model_id",
            "内部模型id": "internal_model_id",
            "厂家": "vendor",
            "供应商": "vendor",
            "manufacturer": "vendor",
            "vendor": "vendor",
            "型号": "model",
            "device_model": "model",
            "model": "model",
            "启用": "enabled",
            "enabled": "enabled",
            "时长_h": "duration_hour",
            "duration_h": "duration_hour",
            "duration_hour": "duration_hour",
            "额定功率_kw": "rated_power_kw",
            "rated_power_kw": "rated_power_kw",
            "额定容量_kwh": "rated_energy_kwh",
            "rated_energy_kwh": "rated_energy_kwh",
            "可用容量_kwh": "usable_energy_kwh_at_fat",
            "usable_energy_kwh_at_fat": "usable_energy_kwh_at_fat",
            "安全等级": "safety_level",
            "safety_level": "safety_level",
            "manual_safety_grade": "manual_safety_grade",
            "ems包": "ems_package",
            "ems_package": "ems_package",
            "ems_package_name": "ems_package_name",
            "价格_元每wh": "price_yuan_per_wh",
            "价格元每wh": "price_yuan_per_wh",
            "price_yuan_per_wh": "price_yuan_per_wh",
            "energy_unit_price_yuan_per_kwh": "energy_unit_price_yuan_per_kwh",
            "cycle_life": "cycle_life",
            "循环寿命": "cycle_life",
            "设计循环寿命": "cycle_life",
            "soc下限": "soc_min",
            "soc_min": "soc_min",
            "最小soc": "soc_min",
            "最小soc比例": "soc_min",
            "soc上限": "soc_max",
            "soc_max": "soc_max",
            "最大soc": "soc_max",
            "最大soc比例": "soc_max",
        }
        if text in alias_map:
            return alias_map[text]
        if text.startswith("电价_"):
            return text.replace(" ", "")
        if text.startswith("h") and len(text) in {2, 3}:
            digits = text[1:]
            if digits.isdigit():
                return f"h{int(digits):02d}"
        return text

    def _parse_date(self, value: Any) -> Optional[date]:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _is_contiguous(self, dates: Sequence[date]) -> bool:
        if not dates:
            return False
        return all(curr - prev == timedelta(days=1) for prev, curr in zip(dates, dates[1:]))

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value in (None, "", "nan"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _value_by_alias(self, row: Dict[str, Any], header_map: Dict[str, str], aliases: Sequence[str]) -> Optional[float]:
        for alias in aliases:
            if alias in header_map:
                return self._coerce_float(row.get(header_map[alias]))
        return None

    def _string_by_alias(self, row: Dict[str, Any], header_map: Dict[str, str], aliases: Sequence[str]) -> Optional[str]:
        for alias in aliases:
            if alias in header_map:
                value = row.get(header_map[alias])
                if value in (None, ""):
                    return None
                return str(value).strip()
        return None

    def _int_by_alias(self, row: Dict[str, Any], header_map: Dict[str, str], aliases: Sequence[str]) -> Optional[int]:
        value = self._value_by_alias(row, header_map, aliases)
        return int(value) if value is not None else None

    def _bool_by_alias(self, row: Dict[str, Any], header_map: Dict[str, str], aliases: Sequence[str], default: bool) -> bool:
        for alias in aliases:
            if alias in header_map:
                value = row.get(header_map[alias])
                if isinstance(value, bool):
                    return value
                text = str(value).strip().lower()
                if text in {"1", "true", "yes", "y", "启用", "是"}:
                    return True
                if text in {"0", "false", "no", "n", "停用", "否"}:
                    return False
        return default
