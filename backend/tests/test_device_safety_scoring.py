from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from storage_engine_project.data.storage_strategy_loader import load_storage_strategies
from storage_engine_project.optimization.device_safety_scoring import (
    DEFAULT_DEVICE_SAFETY_WEIGHTS,
    DeviceSafetyConfig,
    DeviceSafetyRule,
    compute_device_safety_cost,
    score_device,
)


def _v2_device_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "enabled": 1,
        "manufacturer": "测试厂商",
        "device_model": "V2Box-100",
        "rated_power_kw": 100,
        "rated_energy_kwh": 215,
        "duration_hour": 2,
        "battery_chemistry": "LFP_314Ah",
        "cooling_class": "pack_liquid_power_air",
        "cooling_note": "PACK液冷，PCS风冷",
        "ip_system": "IP55",
        "ip_pack": "IP67",
        "ip_pcs": "IP66",
        "corrosion_grade": "C3",
        "corrosion_optional_grade": "C5",
        "manual_safety_grade": "A",
        "round_trip_efficiency": 0.88,
        "c_rate_charge_max": 0.5,
        "c_rate_discharge_max": 0.5,
        "energy_unit_price_yuan_per_kwh": 760,
        "power_related_capex_yuan_per_kw": 260,
        "annual_om_ratio": 0.02,
        "soc_min": 0.1,
        "soc_max": 0.9,
        "operating_temp_min_c": -20,
        "operating_temp_max_c": 55,
        "cycle_life": 8000,
        "fire_detection_class": "composite_detection",
        "fire_suppression_class": "aerosol",
        "explosion_protection_class": "undisclosed",
        "propagation_protection_class": "pack_level",
        "ems_model": "EMS300CP",
        "certification_tokens": "GB_T_36276;IEC_62619",
        "weight_kg": 2600,
        "dimensions_mm": "1500x1300x2300",
        "is_default_candidate": 1,
        "ems_package_name": "EMS-A",
    }
    row.update(overrides)
    return row


def _write_v2_strategy_library(
    path: Path,
    *,
    device_overrides: dict[str, Any] | None = None,
    weights: list[dict[str, Any]] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> None:
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(
            [
                {"key": "schema_version", "value": "device_library_v2", "说明": "schema"},
                {"key": "template_version", "value": "2026.06", "说明": "template"},
            ]
        ).to_excel(writer, sheet_name="元数据", index=False)
        pd.DataFrame([_v2_device_row(**(device_overrides or {}))]).to_excel(
            writer,
            sheet_name="设备库",
            index=False,
        )
        pd.DataFrame(
            weights
            or [
                {"dimension": "thermal", "label_zh": "热管理", "default_weight": 0.5},
                {"dimension": "certification", "label_zh": "认证", "default_weight": 0.5},
            ]
        ).to_excel(writer, sheet_name="安全权重", index=False)
        pd.DataFrame(
            rules
            or [
                {
                    "dimension": "thermal",
                    "source_column": "cooling_class",
                    "pattern": "^pack_liquid_power_air$",
                    "score": 85,
                    "priority": 7,
                    "note": "PACK液冷",
                },
                {
                    "dimension": "thermal",
                    "source_column": "cooling_class",
                    "pattern": "",
                    "score": 60,
                    "priority": 0,
                    "note": "冷却默认",
                },
                {
                    "dimension": "certification",
                    "source_column": "certification_tokens",
                    "pattern": "GB_T_36276",
                    "score": 20,
                    "priority": 10,
                    "note": "GB",
                },
                {
                    "dimension": "certification",
                    "source_column": "certification_tokens",
                    "pattern": "IEC_62619",
                    "score": 25,
                    "priority": 10,
                    "note": "IEC",
                },
                {
                    "dimension": "certification",
                    "source_column": "certification_tokens",
                    "pattern": "",
                    "score": 0,
                    "priority": 0,
                    "note": "未披露",
                },
            ]
        ).to_excel(writer, sheet_name="安全评分规则", index=False)


def test_default_device_safety_weights_match_strategy_library_defaults() -> None:
    assert DEFAULT_DEVICE_SAFETY_WEIGHTS["bms"] == pytest.approx(0.12)
    assert DEFAULT_DEVICE_SAFETY_WEIGHTS["ip"] == pytest.approx(0.05)
    assert DEFAULT_DEVICE_SAFETY_WEIGHTS["corrosion"] == pytest.approx(0.03)
    assert DEFAULT_DEVICE_SAFETY_WEIGHTS["certification"] == pytest.approx(0.05)
    assert sum(DEFAULT_DEVICE_SAFETY_WEIGHTS.values()) == pytest.approx(1.0)


def test_device_safety_scoring_handles_v2_threshold_ip_and_certification_sum() -> None:
    config = DeviceSafetyConfig(
        weights={
            "temp_range": 0.25,
            "ip": 0.25,
            "certification": 0.50,
        },
        rules=[
            DeviceSafetyRule("temp_range", "operating_temp_range_c", ">=75", 85.0, 10, "温差达标"),
            DeviceSafetyRule("temp_range", "operating_temp_range_c", "", 70.0, 0, "温差默认"),
            DeviceSafetyRule("ip", "ip_system", "^IP55$", 80.0, 10, "系统 IP55"),
            DeviceSafetyRule("ip", "ip_system", "^IP67$", 95.0, 9, "系统 IP67"),
            DeviceSafetyRule("ip", "ip_system", "", 60.0, 0, "IP 默认"),
            DeviceSafetyRule("certification", "certification_tokens", "UL9540A", 25.0, 10, "UL"),
            DeviceSafetyRule("certification", "certification_tokens", "IEC62619", 25.0, 10, "IEC62619"),
            DeviceSafetyRule("certification", "certification_tokens", "", 0.0, 0, "未披露安全认证"),
        ],
    )

    scores = score_device(
        {
            "operating_temp_min_c": -20,
            "operating_temp_max_c": 55,
            "ip_system": "IP55",
            "certification_tokens": "UL9540A;IEC62619",
        },
        config,
    )

    assert scores.sub_scores["temp_range"] == pytest.approx(85.0)
    assert scores.sub_scores["ip"] == pytest.approx(80.0)
    assert scores.sub_scores["certification"] == pytest.approx(50.0)
    assert scores.device_safety_cost == pytest.approx(compute_device_safety_cost(scores.sub_scores, config.weights))


def test_device_safety_scoring_prefers_v2_specific_rule() -> None:
    config = DeviceSafetyConfig(
        weights={
            "thermal": 0.5,
            "corrosion": 0.5,
        },
        rules=[
            DeviceSafetyRule("thermal", "cooling_class", "liquid", 90.0, 7, "液冷通用"),
            DeviceSafetyRule("thermal", "cooling_class", "pack_liquid_power_air", 85.0, 7, "PACK液冷"),
            DeviceSafetyRule("thermal", "cooling_class", "", 60.0, 0, "冷却默认"),
            DeviceSafetyRule("corrosion", "corrosion_grade", "^C5$", 95.0, 10, "C5"),
            DeviceSafetyRule("corrosion", "corrosion_grade", "^C3$", 75.0, 7, "C3"),
            DeviceSafetyRule("corrosion", "corrosion_grade", "", 50.0, 0, "防腐默认"),
        ],
    )

    scores = score_device(
        {
            "cooling_class": "pack_liquid_power_air",
            "corrosion_grade": "C3",
        },
        config,
    )

    assert scores.sub_scores["thermal"] == pytest.approx(85.0)
    assert scores.trace["thermal"] == ["PACK液冷"]
    assert scores.sub_scores["corrosion"] == pytest.approx(75.0)
    assert scores.trace["corrosion"] == ["C3"]


def test_v2_strategy_library_loads_device_safety(tmp_path) -> None:
    path = tmp_path / "strategy_v2.xlsx"
    _write_v2_strategy_library(path)

    strategy = load_storage_strategies(path)["测试厂商_V2Box-100"]

    assert strategy.cooling_mode == "pack_liquid_power_air"
    assert strategy.metadata["ip_system"] == "IP55"
    assert strategy.metadata["corrosion_grade"] == "C3"
    assert strategy.metadata["certification_tokens"] == "GB_T_36276;IEC_62619"
    assert strategy.device_safety_available is True
    assert strategy.device_safety_sub_scores["thermal"] == pytest.approx(85.0)
    assert strategy.device_safety_sub_scores["certification"] == pytest.approx(45.0)


def test_device_safety_metric_weight_override_changes_loaded_strategy_score(tmp_path) -> None:
    path = tmp_path / "strategy_v2.xlsx"
    _write_v2_strategy_library(
        path,
        weights=[
            {"dimension": "cell", "label_zh": "电芯", "default_weight": 0.5},
            {"dimension": "certification", "label_zh": "认证", "default_weight": 0.5},
        ],
        rules=[
            {
                "dimension": "cell",
                "source_column": "battery_chemistry",
                "pattern": "LFP",
                "score": 90,
                "priority": 5,
                "note": "LFP",
            },
            {
                "dimension": "cell",
                "source_column": "battery_chemistry",
                "pattern": "",
                "score": 50,
                "priority": 0,
                "note": "未知",
            },
            {
                "dimension": "certification",
                "source_column": "certification_tokens",
                "pattern": "GB_T_36276",
                "score": 20,
                "priority": 10,
                "note": "GB",
            },
            {
                "dimension": "certification",
                "source_column": "certification_tokens",
                "pattern": "",
                "score": 0,
                "priority": 0,
                "note": "未披露",
            },
        ],
    )

    baseline = load_storage_strategies(path)["测试厂商_V2Box-100"]
    override_weights = {key: 0.0 for key in DEFAULT_DEVICE_SAFETY_WEIGHTS}
    override_weights["cell"] = 1.0
    override = load_storage_strategies(
        path,
        device_safety_metric_weights=override_weights,
    )["测试厂商_V2Box-100"]

    assert override.device_safety_weighted_score == pytest.approx(90.0)
    assert override.device_safety_cost < baseline.device_safety_cost


def test_non_v2_strategy_library_is_rejected(tmp_path) -> None:
    path = tmp_path / "legacy_strategy.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([{"enabled": 1, "manufacturer": "旧厂商", "device_model": "Old"}]).to_excel(
            writer,
            sheet_name="设备库",
            index=False,
        )

    with pytest.raises(ValueError, match="device_library_v2"):
        load_storage_strategies(path)
