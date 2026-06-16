from __future__ import annotations

import numpy as np
import pandas as pd

from storage_engine_project.optimization.objective_scoring import (
    annotate_dataframe_scores,
    compute_weighted_objective_scores,
)


def test_direct_and_dataframe_scores_match_for_missing_irr() -> None:
    npv_vals = [5_000_000.0, 8_000_000.0, 6_000_000.0]
    irr_vals = [0.12, None, 0.08]
    payback_vals = [3.0, 5.0, 4.0]
    invest_vals = [11_173_000.0, 20_352_400.0, 15_000_000.0]
    zeros = [0.0, 0.0, 0.0]

    direct = compute_weighted_objective_scores(
        npv=npv_vals,
        irr=[0.12, 0.0, 0.08],
        payback=payback_vals,
        investment=invest_vals,
        transformer=zeros,
        voltage=zeros,
        line=zeros,
        cycle=zeros,
    )

    df = pd.DataFrame(
        {
            "npv_yuan": npv_vals,
            "irr": irr_vals,
            "simple_payback_years": payback_vals,
            "initial_investment_yuan": invest_vals,
            "transformer_violation_hours": zeros,
            "voltage_violation_pu": zeros,
            "line_loading_violation_pct": zeros,
            "cycle_violation": zeros,
            "duration_violation_h": zeros,
            "feasible": [True, True, True],
            "obj_payback": payback_vals,
        }
    )

    annotated = annotate_dataframe_scores(df)

    assert np.allclose(direct.compromise_cost, annotated["compromise_cost"].to_numpy(), atol=1e-9)
    assert np.allclose(direct.fitness_score * 100.0, annotated["fitness_score_pct"].to_numpy(), atol=1e-9)


def test_dataframe_scores_annotate_infeasible_fallback_without_missing_columns() -> None:
    annotated = annotate_dataframe_scores(
        pd.DataFrame(
            {
                "strategy_id": ["larger_violation", "smaller_violation"],
                "feasible": [False, False],
                "total_violation": [8.0, 2.0],
            }
        )
    )

    assert annotated.loc[1, "fitness_score"] > annotated.loc[0, "fitness_score"]
    assert annotated.loc[1, "compromise_cost"] < annotated.loc[0, "compromise_cost"]
    for column in (
        "economic_cost",
        "safety_cost",
        "objective_npv_cost",
        "objective_cycle_score_pct",
    ):
        assert column in annotated.columns


def test_dataframe_scores_use_annual_cycles_for_device_strategy_safety() -> None:
    annotated = annotate_dataframe_scores(
        pd.DataFrame(
            {
                "strategy_id": ["high_economy_high_cycle", "lower_economy_low_cycle"],
                "npv_yuan": [900_000.0, 700_000.0],
                "irr": [0.18, 0.12],
                "simple_payback_years": [3.0, 5.0],
                "initial_investment_yuan": [900_000.0, 1_200_000.0],
                "annual_equivalent_full_cycles": [620.0, 260.0],
                "transformer_violation_hours": [0.0, 0.0],
                "voltage_violation_pu": [0.0, 0.0],
                "line_loading_violation_pct": [0.0, 0.0],
                "cycle_violation": [0.0, 0.0],
                "duration_violation_h": [0.0, 0.0],
                "feasible": [True, True],
            }
        ),
        safety_economy_tradeoff=1.0,
        safety_metric_weights={"transformer": 0.0, "voltage": 0.0, "line": 0.0, "cycle": 1.0},
    )

    high_cycle = annotated.loc[0]
    low_cycle = annotated.loc[1]
    assert low_cycle["objective_cycle_cost"] < high_cycle["objective_cycle_cost"]
    assert low_cycle["fitness_score"] > high_cycle["fitness_score"]


def test_dataframe_scores_fall_back_to_objective_safety_when_cycles_missing() -> None:
    annotated = annotate_dataframe_scores(
        pd.DataFrame(
            {
                "strategy_id": ["higher_proxy", "lower_proxy"],
                "npv_yuan": [900_000.0, 700_000.0],
                "irr": [0.18, 0.12],
                "simple_payback_years": [3.0, 5.0],
                "initial_investment_yuan": [900_000.0, 1_200_000.0],
                "obj_safety": [12.0, 2.0],
                "cycle_violation": [0.0, 0.0],
                "duration_violation_h": [0.0, 0.0],
                "feasible": [True, True],
            }
        ),
        safety_economy_tradeoff=1.0,
        safety_metric_weights={"transformer": 0.0, "voltage": 0.0, "line": 0.0, "cycle": 1.0},
    )

    assert annotated.loc[1, "objective_cycle_cost"] < annotated.loc[0, "objective_cycle_cost"]
    assert annotated.loc[1, "fitness_score"] > annotated.loc[0, "fitness_score"]


def test_device_safety_beta_zero_preserves_existing_weighted_scores() -> None:
    common = dict(
        npv=[100_000.0, 100_000.0],
        irr=[0.1, 0.1],
        payback=[5.0, 5.0],
        investment=[500_000.0, 500_000.0],
        transformer=[0.0, 0.0],
        voltage=[0.0, 0.0],
        line=[0.0, 0.0],
        cycle=[0.0, 0.0],
        safety_economy_tradeoff=1.0,
    )
    baseline = compute_weighted_objective_scores(**common)
    with_device_safety_disabled = compute_weighted_objective_scores(
        **common,
        device_safety_cost=[0.0, 1.0],
        device_safety_beta=0.0,
    )

    assert np.allclose(baseline.compromise_cost, with_device_safety_disabled.compromise_cost)
    assert with_device_safety_disabled.device_safety_beta == 0.0


def test_device_safety_cost_can_affect_safety_score_when_available() -> None:
    scores = compute_weighted_objective_scores(
        npv=[100_000.0, 100_000.0],
        irr=[0.1, 0.1],
        payback=[5.0, 5.0],
        investment=[500_000.0, 500_000.0],
        transformer=[0.0, 0.0],
        voltage=[0.0, 0.0],
        line=[0.0, 0.0],
        cycle=[0.0, 0.0],
        safety_economy_tradeoff=1.0,
        device_safety_cost=[0.1, 0.8],
        device_safety_beta=0.5,
    )

    assert scores.safety_cost[0] < scores.safety_cost[1]
    assert scores.fitness_score[0] > scores.fitness_score[1]
    assert scores.device_safety_beta == 0.5


def test_dataframe_scores_do_not_invent_device_safety_for_legacy_rows() -> None:
    annotated = annotate_dataframe_scores(
        pd.DataFrame(
            {
                "strategy_id": ["legacy_a", "legacy_b"],
                "npv_yuan": [100_000.0, 100_000.0],
                "irr": [0.1, 0.1],
                "simple_payback_years": [5.0, 5.0],
                "initial_investment_yuan": [500_000.0, 500_000.0],
                "transformer_violation_hours": [0.0, 0.0],
                "voltage_violation_pu": [0.0, 0.0],
                "line_loading_violation_pct": [0.0, 0.0],
                "cycle_violation": [0.0, 0.0],
                "duration_violation_h": [0.0, 0.0],
                "device_safety_cost": [0.1, 0.8],
                "device_safety_available": [False, False],
                "feasible": [True, True],
            }
        )
    )

    assert annotated["device_safety_beta"].dropna().eq(0.0).all()
    assert annotated["fitness_score"].nunique() == 1
