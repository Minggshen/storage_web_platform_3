from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from storage_engine_project.simulation.opendss_network_constraint_oracle import (
    OpenDSSConstraintOracle,
    OpenDSSOracleConfig,
)


def _write_runtime_files(node_dir) -> None:
    node_dir.mkdir()
    (node_dir / "runtime_year_model_map.csv").write_text(
        "\n".join(
            ["day_index,internal_model_id"]
            + [f"{day},{1 if day < 200 else 2}" for day in range(365)]
        ),
        encoding="utf-8",
    )
    hour_cols = ",".join(f"h{hour:02d}" for hour in range(24))
    model_1 = ",".join(str(100 + hour) for hour in range(24))
    model_2 = ",".join(str(200 + hour) for hour in range(24))
    (node_dir / "runtime_model_library.csv").write_text(
        "\n".join(
            [
                f"internal_model_id,{hour_cols}",
                f"1,{model_1}",
                f"2,{model_2}",
            ]
        ),
        encoding="utf-8",
    )


def test_runtime_manifest_precomputes_net_load_matrix(tmp_path) -> None:
    node_dir = tmp_path / "node"
    _write_runtime_files(node_dir)
    manifest_path = tmp_path / "network_runtime_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "loads": [
                    {
                        "enabled": True,
                        "node_dir": str(node_dir),
                        "year_model_map_file": "runtime_year_model_map.csv",
                        "model_library_file": "runtime_model_library.csv",
                        "dss_load_name": "load.node",
                        "dss_bus_name": "bus.node",
                        "pv_capacity_kw": 24.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    oracle = OpenDSSConstraintOracle.__new__(OpenDSSConstraintOracle)
    oracle.config = OpenDSSOracleConfig(master_dss_path=str(tmp_path / "Master.dss"))
    oracle.master_dss_path = str(tmp_path / "Master.dss")
    oracle._runtime_manifest_cache = {}

    ctx = SimpleNamespace(meta={"network_runtime_manifest_path": str(manifest_path)})
    entries = oracle._load_network_runtime_entries(ctx)

    assert len(entries) == 1
    matrix = entries[0]["runtime_net_load_matrix_kw"]
    assert matrix.shape == (365, 24)
    assert oracle._runtime_kw_for_hour(entries[0], 0, 0) == pytest.approx(100.0)
    assert oracle._runtime_kw_for_hour(entries[0], 200, 12) == pytest.approx(212.0 - 24.0)
    assert oracle._runtime_kw_for_hour(entries[0], 200, 18) == pytest.approx(218.0)
