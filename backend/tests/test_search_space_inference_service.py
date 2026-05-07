from __future__ import annotations

import os
import sys

import pytest

# Allow `from services...` imports when pytest runs from repo root.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.search_space_inference_service import (  # noqa: E402
    SearchSpaceInferenceService,
    SearchSpaceInferenceResult,
)


def _device(
    *,
    enabled: bool = True,
    duration_hour: float | None = None,
    rated_power_kw: float | None = None,
    rated_energy_kwh: float | None = None,
    vendor: str = "V",
    model: str = "M",
) -> dict[str, object]:
    return {
        "enabled": enabled,
        "vendor": vendor,
        "model": model,
        "duration_hour": duration_hour,
        "rated_power_kw": rated_power_kw,
        "rated_energy_kwh": rated_energy_kwh,
    }


@pytest.fixture
def service() -> SearchSpaceInferenceService:
    return SearchSpaceInferenceService()


def test_infer_uses_min_of_runtime_transformer_grid_for_upper(service):
    # transformer_limit_kw = 1000 * 0.95 * (1 - 0.1) = 855
    result = service.infer(
        node_params={},
        runtime_stats={'peak_kw': 700.0, 'valley_kw': 50.0, 'annual_mean_kw': 300.0, 'mean_daily_energy_kwh': 6000.0},
        device_records=[_device(duration_hour=2.0), _device(duration_hour=4.0, model='M2')],
        transformer_capacity_kva=1000.0,
        transformer_pf_limit=0.95,
        transformer_reserve_ratio=0.1,
        grid_interconnection_limit_kw=900.0,
    )
    assert isinstance(result, SearchSpaceInferenceResult)
    # min(700, 855, 900) = 700
    assert result.device_power_max_kw == pytest.approx(700.0)
    assert result.transformer_limit_kw == pytest.approx(855.0)
    assert 'runtime_peak' in result.source
    assert 'transformer_limit' in result.source
    assert 'grid_limit' in result.source
    power_upper = next(item for item in result.explain if item["boundary"] == "device_power_max_kw")
    assert power_upper["decisive_constraint"] == "runtime_peak"
    assert power_upper["final_value"] == pytest.approx(700.0)


def test_infer_fallback_default_when_no_info_records_note(service):
    result = service.infer(
        node_params={},
        runtime_stats=None,
        device_records=[],
        transformer_capacity_kva=None,
        transformer_pf_limit=None,
        transformer_reserve_ratio=None,
        grid_interconnection_limit_kw=None,
    )
    assert result.device_power_max_kw == pytest.approx(500.0)
    assert any('500' in n for n in result.notes)
    assert 'default_power_upper' in result.source
    assert any(item["boundary"] == "search_duration_max_h" for item in result.explain)
    # default duration window from service
    assert result.search_duration_min_h == pytest.approx(2.0)
    assert result.search_duration_max_h == pytest.approx(4.0)


def test_infer_duration_from_device_records(service):
    # one device with duration_hour, one with rated_power+rated_energy → duration = 5/2 = 2.5
    result = service.infer(
        node_params={},
        runtime_stats={'peak_kw': 400.0},
        device_records=[
            _device(duration_hour=3.0),
            _device(rated_power_kw=2.0, rated_energy_kwh=5.0, model='M2'),
            _device(duration_hour=6.0, model='M3'),
        ],
        transformer_capacity_kva=None,
        transformer_pf_limit=None,
        transformer_reserve_ratio=None,
        grid_interconnection_limit_kw=None,
    )
    assert result.search_duration_min_h == pytest.approx(2.5)
    assert result.search_duration_max_h >= 6.0


def test_infer_disabled_device_records_ignored(service):
    result = service.infer(
        node_params={},
        runtime_stats={'peak_kw': 400.0},
        device_records=[
            _device(duration_hour=1.0, enabled=False),
            _device(duration_hour=3.0, model='M2'),
            _device(duration_hour=5.0, model='M3'),
        ],
        transformer_capacity_kva=None,
        transformer_pf_limit=None,
        transformer_reserve_ratio=None,
        grid_interconnection_limit_kw=None,
    )
    # disabled 1.0h must be ignored → min should be 3.0
    assert result.search_duration_min_h == pytest.approx(3.0)


def test_infer_does_not_mutate_node_params(service):
    node_params = {'legacy_manual_override_kw': 999.0, 'foo': 'bar'}
    snapshot = dict(node_params)
    service.infer(
        node_params=node_params,
        runtime_stats={'peak_kw': 400.0},
        device_records=[_device(duration_hour=2.0)],
        transformer_capacity_kva=500.0,
        transformer_pf_limit=0.9,
        transformer_reserve_ratio=0.1,
        grid_interconnection_limit_kw=None,
    )
    assert node_params == snapshot


def test_infer_power_min_floor_30kw(service):
    # Tiny peak → power_min would be far below 30, must be clamped to 30.
    result = service.infer(
        node_params={},
        runtime_stats={'peak_kw': 100.0},
        device_records=[_device(duration_hour=2.0)],
        transformer_capacity_kva=None,
        transformer_pf_limit=None,
        transformer_reserve_ratio=None,
        grid_interconnection_limit_kw=None,
    )
    assert result.search_power_min_kw >= 30.0
    # And upper must remain ≥ lower (service guarantees this)
    assert result.device_power_max_kw >= result.search_power_min_kw


def test_infer_duration_max_ge_min_and_source_nonempty(service):
    result = service.infer(
        node_params={},
        runtime_stats={'peak_kw': 600.0, 'mean_daily_energy_kwh': 4000.0},
        device_records=[_device(duration_hour=2.0), _device(duration_hour=4.0, model='M2')],
        transformer_capacity_kva=800.0,
        transformer_pf_limit=0.9,
        transformer_reserve_ratio=0.1,
        grid_interconnection_limit_kw=None,
    )
    assert result.search_duration_max_h >= result.search_duration_min_h
    assert isinstance(result.source, str) and result.source


def test_infer_explain_marks_duration_anchor_as_decisive(service):
    result = service.infer(
        node_params={},
        runtime_stats={'peak_kw': 400.0, 'mean_daily_energy_kwh': 4000.0},
        device_records=[_device(duration_hour=2.0), _device(duration_hour=4.0, model='M2')],
        transformer_capacity_kva=None,
        transformer_pf_limit=None,
        transformer_reserve_ratio=None,
        grid_interconnection_limit_kw=None,
    )
    duration_max = next(item for item in result.explain if item["boundary"] == "search_duration_max_h")
    assert duration_max["decisive_constraint"] == "runtime_daily_energy_anchor"
    assert duration_max["final_value"] == pytest.approx(8.0)
