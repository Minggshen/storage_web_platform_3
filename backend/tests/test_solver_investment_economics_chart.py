from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

# Allow `from services...` imports when pytest runs from repo root.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

_project_model_stub = types.ModuleType("services.project_model_service")
_project_model_stub.ProjectModelService = type("ProjectModelService", (), {})
sys.modules.setdefault("services.project_model_service", _project_model_stub)

from services.solver_execution_service import SolverExecutionService  # noqa: E402


def test_runtime_command_uses_request_objective_weights(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    task_workspace = tmp_path / "workspace"
    output_dir = tmp_path / "outputs"
    request = {
        "target_id": "case-a",
        "solver_tier": "delivery",
        "safety_economy_tradeoff": 0.73,
        "economic_weight_npv": 0.11,
        "economic_weight_irr": 0.22,
        "economic_weight_payback": 0.33,
        "economic_weight_investment": 0.44,
        "safety_weight_transformer": 0.15,
        "safety_weight_voltage": 0.25,
        "safety_weight_line": 0.35,
        "safety_weight_cycle": 0.45,
    }

    command = service._build_runtime_command(
        python_executable="python",
        solver_project_root=tmp_path / "storage_engine_project",
        task_workspace=task_workspace,
        output_dir=output_dir,
        request=request,
    )

    option_values = {
        str(command[index]): str(command[index + 1])
        for index in range(len(command) - 1)
        if str(command[index]).startswith("--")
    }
    assert option_values["--safety-economy-tradeoff"] == "0.73"
    assert option_values["--economic-weight-npv"] == "0.11"
    assert option_values["--economic-weight-irr"] == "0.22"
    assert option_values["--economic-weight-payback"] == "0.33"
    assert option_values["--economic-weight-investment"] == "0.44"
    assert option_values["--safety-weight-transformer"] == "0.15"
    assert option_values["--safety-weight-voltage"] == "0.25"
    assert option_values["--safety-weight-line"] == "0.35"
    assert option_values["--safety-weight-cycle"] == "0.45"


def test_investment_economics_chart_marks_highest_fitness_candidate(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    rows = [
        {
            "strategy_id": "low_invest",
            "rated_power_kw": 100,
            "rated_energy_kwh": 200,
            "duration_h": 2,
            "npv_yuan": 120_000,
            "initial_investment_yuan": 800_000,
            "annualized_net_cashflow_yuan": 95_000,
            "irr": 0.10,
            "simple_payback_years": 5.2,
            "discounted_payback_years": 6.4,
            "obj_safety": 4.0,
            "feasible": True,
            "total_violation": 0,
        },
        {
            "strategy_id": "balanced",
            "rated_power_kw": 160,
            "rated_energy_kwh": 320,
            "duration_h": 2,
            "npv_yuan": 260_000,
            "initial_investment_yuan": 1_300_000,
            "annualized_net_cashflow_yuan": 150_000,
            "irr": 0.13,
            "simple_payback_years": 4.4,
            "discounted_payback_years": 5.2,
            "obj_safety": 1.5,
            "feasible": True,
            "total_violation": 0,
        },
        {
            "strategy_id": "high_invest",
            "rated_power_kw": 280,
            "rated_energy_kwh": 560,
            "duration_h": 2,
            "npv_yuan": 300_000,
            "initial_investment_yuan": 2_000_000,
            "annualized_net_cashflow_yuan": 170_000,
            "irr": 0.09,
            "simple_payback_years": 7.0,
            "discounted_payback_years": 8.6,
            "obj_safety": 0.4,
            "feasible": True,
            "total_violation": 0,
        },
    ]

    pareto = service._build_pareto_chart(rows, safety_economy_tradeoff=0.5)
    economics = service._build_investment_economics_chart(pareto)
    summary = service._build_investment_economics_summary(economics, safety_economy_tradeoff=0.5)

    assert len(economics) == len(rows)
    assert [row["strategyId"] for row in economics] == ["low_invest", "balanced", "high_invest"]
    best = next(row for row in economics if row["objectiveBest"] is True)
    assert best["fitnessRank"] == 1
    assert best["fitnessScorePct"] == max(row["fitnessScorePct"] for row in economics)
    assert best["fitnessScorePct"] == pytest.approx(best["fitnessScore"] * 100.0)
    assert best["economicScorePct"] == pytest.approx(best["economicScore"] * 100.0)
    assert best["safetyScorePct"] == pytest.approx(best["safetyScore"] * 100.0)
    assert best["objectiveNpvScorePct"] == pytest.approx((1.0 - best["objectiveNpvCost"]) * 100.0)
    assert best["objectivePaybackScorePct"] == pytest.approx((1.0 - best["objectivePaybackCost"]) * 100.0)
    assert best["compromiseCost"] == pytest.approx(1.0 - best["fitnessScore"])
    assert summary["bestStrategyId"] == best["strategyId"]
    assert summary["feasibleCount"] == 3
    assert summary["economicWeight"] == 0.5
    assert summary["safetyWeight"] == 0.5
    assert summary["economicWeightNpv"] > 0
    assert summary["safetyWeightCycle"] > 0


def test_investment_economics_chart_prefers_precomputed_csv_scores(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    rows = [
        {
            "strategy_id": "csv_best",
            "rated_power_kw": 100,
            "rated_energy_kwh": 200,
            "duration_h": 2,
            "npv_yuan": 10_000,
            "initial_investment_yuan": 900_000,
            "irr": 0.02,
            "simple_payback_years": 9.0,
            "feasible": True,
            "total_violation": 0.0,
            "fitness_score": 0.91,
            "fitness_score_pct": 91.0,
            "compromise_cost": 0.09,
            "economic_cost": 0.20,
            "safety_cost": 0.00,
        },
        {
            "strategy_id": "recompute_would_win",
            "rated_power_kw": 180,
            "rated_energy_kwh": 360,
            "duration_h": 2,
            "npv_yuan": 900_000,
            "initial_investment_yuan": 1_000_000,
            "irr": 0.20,
            "simple_payback_years": 2.0,
            "feasible": True,
            "total_violation": 0.0,
            "fitness_score": 0.25,
            "fitness_score_pct": 25.0,
            "compromise_cost": 0.75,
            "economic_cost": 0.00,
            "safety_cost": 0.00,
        },
    ]

    pareto = service._build_pareto_chart(rows, safety_economy_tradeoff=0.0)
    economics = service._build_investment_economics_chart(pareto)
    best = next(row for row in economics if row["objectiveBest"] is True)

    assert best["strategyId"] == "csv_best"
    assert best["fitnessScore"] == pytest.approx(0.91)
    assert best["fitnessScorePct"] == pytest.approx(91.0)
    assert best["compromiseCost"] == pytest.approx(0.09)
    assert best["economicScore"] == pytest.approx(0.80)
    assert best["economicScorePct"] == pytest.approx(80.0)


def test_investment_economics_chart_uses_objective_safety_when_violations_are_zero(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    rows = [
        {
            "strategy_id": "high_economy_high_safety_proxy",
            "rated_power_kw": 100,
            "rated_energy_kwh": 200,
            "duration_h": 2,
            "npv_yuan": 900_000,
            "initial_investment_yuan": 900_000,
            "irr": 0.18,
            "simple_payback_years": 3.0,
            "obj_safety": 620.0,
            "cycle_violation": 0.0,
            "duration_violation_h": 0.0,
            "feasible": True,
            "total_violation": 0.0,
        },
        {
            "strategy_id": "lower_economy_low_safety_proxy",
            "rated_power_kw": 120,
            "rated_energy_kwh": 240,
            "duration_h": 2,
            "npv_yuan": 700_000,
            "initial_investment_yuan": 1_200_000,
            "irr": 0.12,
            "simple_payback_years": 5.0,
            "obj_safety": 260.0,
            "cycle_violation": 0.0,
            "duration_violation_h": 0.0,
            "feasible": True,
            "total_violation": 0.0,
        },
    ]

    pareto = service._build_pareto_chart(
        rows,
        safety_economy_tradeoff=1.0,
        safety_metric_weights={"transformer": 0.0, "voltage": 0.0, "line": 0.0, "cycle": 1.0},
    )
    economics = service._build_investment_economics_chart(pareto)
    best = next(row for row in economics if row["objectiveBest"] is True)

    assert best["strategyId"] == "lower_economy_low_safety_proxy"
    assert best["objectiveSafetyCycleCost"] == pytest.approx(0.0)
    other = next(row for row in economics if row["strategyId"] == "high_economy_high_safety_proxy")
    assert other["objectiveSafetyCycleCost"] == pytest.approx(1.0)


def test_investment_economics_chart_restores_legacy_best_when_scores_are_missing(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    rows = [
        {
            "strategy_id": "比亚迪储能_IC07-B233AP125-A-R2",
            "rated_power_kw": 1050.0,
            "rated_energy_kwh": 2362.5,
            "duration_h": 2.25,
            "npv_yuan": 1_949_610.2209600292,
            "initial_investment_yuan": 2_757_368.25,
            "irr": 0.18,
            "simple_payback_years": 4.737458536978171,
            "obj_safety": 666.0009853463039,
            "annual_equivalent_full_cycles": 666.0009853463039,
            "feasible": True,
            "total_violation": 0.0,
        },
        {
            "strategy_id": "阳光电源_ST510CS-4H-CN",
            "rated_power_kw": 4800.0,
            "rated_energy_kwh": 19200.0,
            "duration_h": 4.0,
            "npv_yuan": 5_747_804.315482914,
            "initial_investment_yuan": 20_352_384.0,
            "irr": 0.10,
            "simple_payback_years": 7.111439301379069,
            "obj_safety": 370.4478380491158,
            "annual_equivalent_full_cycles": 370.4478380491158,
            "feasible": True,
            "total_violation": 0.0,
        },
    ]
    best_summary = {
        "strategy_id": "阳光电源_ST510CS-4H-CN",
        "rated_power_kw": 4800.0,
        "rated_energy_kwh": 19200.0,
    }

    pareto = service._build_pareto_chart(
        rows,
        safety_economy_tradeoff=0.9,
        best_result_summary=best_summary,
    )
    economics = service._build_investment_economics_chart(pareto)
    summary = service._build_investment_economics_summary(economics, safety_economy_tradeoff=0.9)
    best = next(row for row in economics if row["objectiveBest"] is True)

    assert best["strategyId"] == "阳光电源_ST510CS-4H-CN"
    assert best["recommendedCandidate"] is True
    assert summary["recommendationMatchesFitness"] is True
    assert summary["scoreSource"] == "legacy_compromise_v1"


def test_investment_economics_chart_uses_violation_fallback_when_no_feasible(tmp_path: Path) -> None:
    service = SolverExecutionService(data_root=tmp_path)
    rows = [
        {
            "strategy_id": "larger_violation",
            "rated_power_kw": 100,
            "rated_energy_kwh": 200,
            "npv_yuan": -10_000,
            "initial_investment_yuan": 800_000,
            "feasible": False,
            "total_violation": 8.0,
        },
        {
            "strategy_id": "smaller_violation",
            "rated_power_kw": 120,
            "rated_energy_kwh": 240,
            "npv_yuan": -20_000,
            "initial_investment_yuan": 950_000,
            "feasible": False,
            "total_violation": 2.0,
        },
    ]

    pareto = service._build_pareto_chart(rows, safety_economy_tradeoff=0.5)
    economics = service._build_investment_economics_chart(pareto)
    best = next(row for row in economics if row["objectiveBest"] is True)

    assert best["strategyId"] == "smaller_violation"
    assert best["fitnessRank"] == 1
