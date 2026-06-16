from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.solver_execution_service import SolverExecutionService  # noqa: E402


def _option_value(command: list[str], option: str) -> str:
    index = command.index(option)
    return command[index + 1]


def test_frontend_solver_run_request_maps_to_solver_cli(tmp_path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    task_workspace = tmp_path / "task" / "solver_workspace"
    output_dir = task_workspace / "outputs" / "integrated_optimization"

    command = service._build_runtime_command(
        python_executable="python",
        solver_project_root=Path("solver_root"),
        task_workspace=task_workspace,
        output_dir=output_dir,
        request={
            "population_size": 9,
            "generations": 4,
            "solver_tier": "custom",
            "target_id": "load_09",
            "initial_soc": 0.25,
            "terminal_soc_mode": "fixed",
            "fixed_terminal_soc_target": 0.55,
            "daily_terminal_soc_tolerance": 0.03,
            "safety_economy_tradeoff": 0.7,
            "economic_weight_npv": 0.4,
            "economic_weight_irr": 0.2,
            "economic_weight_payback": 0.3,
            "economic_weight_investment": 0.1,
            "safety_weight_transformer": 0.1,
            "safety_weight_voltage": 0.2,
            "safety_weight_line": 0.3,
            "safety_weight_cycle": 0.4,
            "device_safety_weight_thermal": 0.14,
            "device_safety_weight_ip": 0.05,
            "device_safety_weight_certification": 0.05,
        },
    )

    assert _option_value(command, "--population-size") == "9"
    assert _option_value(command, "--generations") == "4"
    assert _option_value(command, "--target-id") == "load_09"
    assert _option_value(command, "--initial-soc") == "0.25"
    assert _option_value(command, "--terminal-soc-mode") == "fixed"
    assert _option_value(command, "--fixed-terminal-soc-target") == "0.55"
    assert _option_value(command, "--daily-terminal-soc-tolerance") == "0.03"
    assert _option_value(command, "--safety-economy-tradeoff") == "0.7"
    assert _option_value(command, "--economic-weight-npv") == "0.4"
    assert _option_value(command, "--safety-weight-line") == "0.3"
    assert _option_value(command, "--device-safety-weight-thermal") == "0.14"
    assert _option_value(command, "--device-safety-weight-ip") == "0.05"
    assert _option_value(command, "--device-safety-weight-certification") == "0.05"


def test_free_terminal_soc_mode_omits_unused_target_and_tolerance(tmp_path) -> None:
    command = SolverExecutionService(data_root=tmp_path)._build_runtime_command(
        python_executable="python",
        solver_project_root=Path("solver_root"),
        task_workspace=tmp_path / "task" / "solver_workspace",
        output_dir=tmp_path / "task" / "solver_workspace" / "outputs" / "integrated_optimization",
        request={
            "population_size": 8,
            "generations": 3,
            "target_id": "load_09",
            "terminal_soc_mode": "free",
            "fixed_terminal_soc_target": 0.8,
            "daily_terminal_soc_tolerance": 0.05,
        },
    )

    assert _option_value(command, "--terminal-soc-mode") == "free"
    assert "--fixed-terminal-soc-target" not in command
    assert "--daily-terminal-soc-tolerance" not in command
