
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage_engine_project.config.operation_config import OperationConfig, get_default_operation_config
from storage_engine_project.config.safety_config import SafetyConfig, get_default_safety_config
from storage_engine_project.config.service_config import ServiceConfig, get_default_service_config
from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.data.context_factory import (
    RegistryScenario,
    build_context_from_registry_scenario,
    build_search_spaces_for_scenario,
    load_registry_scenarios,
)
from storage_engine_project.optimization.optimizer_bridge import SearchSpaceConfig


@dataclass(slots=True)
class OptimizationCase:
    registry_scenario: RegistryScenario
    context: AnnualOperationContext
    search_spaces: dict[str, SearchSpaceConfig]

    @property
    def internal_model_id(self) -> str:
        return self.registry_scenario.internal_model_id

    @property
    def strategy_candidates(self) -> list[str]:
        return list(self.search_spaces.keys())


def _normalize_base_dir(registry_path: Path, base_dir: str | Path | None) -> Path:
    """
    统一归一化到工程根目录。
    registry_path 通常形如 project/inputs/registry/node_registry.xlsx
    """
    if base_dir is None:
        if registry_path.parent.name == "registry":
            return registry_path.parent.parent.parent
        return registry_path.parent

    p = Path(base_dir).resolve()
    if p.name == "registry":
        return p.parent.parent
    if p.name == "inputs":
        return p.parent
    return p


def load_optimization_cases(
    registry_path: str | Path,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    base_dir: str | Path | None = None,
    operation_config: OperationConfig | None = None,
    safety_config: SafetyConfig | None = None,
    service_config: ServiceConfig | None = None,
    only_enabled_and_optimizable: bool = True,
) -> list[OptimizationCase]:
    registry_path = Path(registry_path).resolve()
    base_dir = _normalize_base_dir(registry_path, base_dir)

    scenarios = load_registry_scenarios(registry_path=registry_path, base_dir=base_dir)
    if only_enabled_and_optimizable:
        scenarios = [s for s in scenarios if s.enabled and s.optimize]

    cases: list[OptimizationCase] = []
    for scenario in scenarios:
        ctx = build_context_from_registry_scenario(
            scenario=scenario,
            strategy_library_path=strategy_library_path,
            operation_config=operation_config or get_default_operation_config(),
            safety_config=safety_config or get_default_safety_config(),
            service_config=service_config or get_default_service_config(),
        )
        search_spaces = build_search_spaces_for_scenario(
            scenario=scenario,
            strategy_library_path=strategy_library_path,
            context=ctx,
        )
        cases.append(
            OptimizationCase(
                registry_scenario=scenario,
                context=ctx,
                search_spaces=search_spaces,
            )
        )
    return cases


def load_single_optimization_case(
    registry_path: str | Path,
    internal_model_id: str,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    base_dir: str | Path | None = None,
    operation_config: OperationConfig | None = None,
    safety_config: SafetyConfig | None = None,
    service_config: ServiceConfig | None = None,
) -> OptimizationCase:
    cases = load_optimization_cases(
        registry_path=registry_path,
        strategy_library_path=strategy_library_path,
        base_dir=base_dir,
        operation_config=operation_config,
        safety_config=safety_config,
        service_config=service_config,
        only_enabled_and_optimizable=False,
    )
    for case in cases:
        if case.internal_model_id == internal_model_id:
            return case
    raise KeyError(f"未找到 internal_model_id={internal_model_id} 的场景。")


def build_case(
    registry_path: str | Path,
    internal_model_id: str,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    **kwargs: Any,
) -> OptimizationCase:
    return load_single_optimization_case(
        registry_path=registry_path,
        internal_model_id=internal_model_id,
        strategy_library_path=strategy_library_path,
        **kwargs,
    )


def build_cases(
    registry_path: str | Path,
    strategy_library_path: str | Path = "inputs/storage/工商业储能设备策略库.xlsx",
    **kwargs: Any,
) -> list[OptimizationCase]:
    return load_optimization_cases(
        registry_path=registry_path,
        strategy_library_path=strategy_library_path,
        **kwargs,
    )
