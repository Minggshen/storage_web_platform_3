from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def extract_topology(project: dict[str, Any]) -> dict[str, Any]:
    network = project.get("network") if isinstance(project.get("network"), dict) else {}
    nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
    edges = network.get("edges") if isinstance(network.get("edges"), list) else []
    economic_params = network.get("economic_parameters") if isinstance(network.get("economic_parameters"), dict) else {}
    return {"nodes": nodes, "edges": edges, "economic_parameters": economic_params}


def stable_hash(payload: Any) -> str:
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def topology_hash(topology: dict[str, Any]) -> str:
    return stable_hash(topology)


def topology_hash_from_project(project: dict[str, Any]) -> str:
    return topology_hash(extract_topology(project))


def build_input_hash(project: dict[str, Any]) -> str:
    return stable_hash(build_input_signature(project))


def build_input_signature(project: dict[str, Any]) -> dict[str, Any]:
    network = project.get("network") if isinstance(project.get("network"), dict) else {}
    nodes = network.get("nodes") if isinstance(network.get("nodes"), list) else []
    assets = project.get("assets") if isinstance(project.get("assets"), dict) else {}
    tariff = project.get("tariff") if isinstance(project.get("tariff"), dict) else {}
    device_library = project.get("device_library") if isinstance(project.get("device_library"), dict) else {}

    load_runtime_assets: list[dict[str, Any]] = []
    for node in nodes:
        if str(node.get("type") or "").strip().lower() != "load":
            continue
        binding = node.get("runtime_binding") if isinstance(node.get("runtime_binding"), dict) else {}
        year_asset_id = str(binding.get("year_map_file_id") or "")
        model_asset_id = str(binding.get("model_library_file_id") or "")
        load_runtime_assets.append(
            {
                "node_id": str(node.get("id") or ""),
                "runtime_binding": binding,
                "year_map_asset": asset_signature(assets.get(year_asset_id)),
                "model_library_asset": asset_signature(assets.get(model_asset_id)),
            }
        )

    return {
        "topology": extract_topology(project),
        "tariff": {
            "tariff_year": tariff.get("tariff_year"),
            "asset": asset_signature(tariff.get("asset")),
        },
        "device_library": {
            "asset": asset_signature(device_library.get("asset")),
            "records": device_library.get("records") if isinstance(device_library.get("records"), list) else [],
        },
        "load_runtime_assets": sorted(load_runtime_assets, key=lambda item: item["node_id"]),
        "solve_config": project.get("solve_config") if isinstance(project.get("solve_config"), dict) else {},
    }


def asset_signature(asset: Any) -> dict[str, Any] | None:
    if not isinstance(asset, dict):
        return None
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    stored_path = metadata.get("stored_path")
    file_stat: dict[str, Any] | None = None
    if stored_path:
        path = Path(str(stored_path))
        try:
            stat = path.stat()
            file_stat = {
                "path": str(path.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        except OSError:
            file_stat = {
                "path": str(path),
                "missing": True,
            }
    return {
        "file_id": asset.get("file_id"),
        "file_name": asset.get("file_name"),
        "source_type": asset.get("source_type"),
        "metadata": metadata,
        "file_stat": file_stat,
    }
