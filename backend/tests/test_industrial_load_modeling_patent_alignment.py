from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _industrial_modeling_module():
    pytest.importorskip("sklearn")
    pytest.importorskip("matplotlib")
    from services import load_modeling_industrial  # noqa: PLC0415

    return load_modeling_industrial


def _week_rows(week_start: date, labels: list[str]) -> list[dict]:
    return [
        {
            "日期": week_start + timedelta(days=idx),
            "星期序号": idx,
            "星期": f"周{idx + 1}",
            "周起始日": week_start,
            "初判周内类别名称": label,
            "初判周内类别编码": {"工作日": 1, "休息日": 2, "同类日": 3}[label],
            "数据质量合格": True,
            "数据质量说明": "质量合格",
            "异常负荷日": False,
        }
        for idx, label in enumerate(labels)
    ]


def test_low_quality_week_uses_main_pattern_and_is_excluded_from_curve_mean() -> None:
    mod = _industrial_modeling_module()
    week1 = date(2025, 1, 6)
    week2 = date(2025, 1, 13)
    weekly_day_result = pd.DataFrame(
        [
            *_week_rows(week1, ["工作日", "工作日", "工作日", "工作日", "工作日", "休息日", "休息日"]),
            *_week_rows(week2, ["休息日", "休息日", "休息日", "休息日", "休息日", "工作日", "工作日"]),
        ]
    )
    week_pattern_df = pd.DataFrame(
        [
            {"周起始日": week1, "初判周模式编码": "WWWWWRR"},
            {"周起始日": week2, "初判周模式编码": "RRRRRWW"},
        ]
    )
    weekly_summary_result = pd.DataFrame(
        [
            {"周起始日": week1, "轮廓系数": 0.2, "数据质量合格": True, "数据质量说明": "质量合格"},
            {"周起始日": week2, "轮廓系数": 0.4, "数据质量合格": False, "数据质量说明": "存在疑似孤立尖峰"},
        ]
    )

    revised = mod.revise_week_labels_by_main_pattern(
        weekly_day_result,
        weekly_summary_result,
        week_pattern_df,
        "WWWWWRR",
    )

    bad_week = revised[revised["周起始日"] == week2].sort_values("星期序号")
    assert bad_week["最终周内类别名称"].tolist() == ["工作日", "工作日", "工作日", "工作日", "工作日", "休息日", "休息日"]
    assert set(bad_week["周类型"]) == {"数据质量修正周"}
    assert bad_week["参与典型曲线建模"].eq(False).all()


def test_sparse_combo_merge_and_curve_mean_use_representative_days() -> None:
    mod = _industrial_modeling_module()
    start = date(2025, 1, 1)
    dates = [start + timedelta(days=i) for i in range(10)]
    rows = []
    for idx, day in enumerate(dates):
        if idx < 4:
            value = 10.0
        elif idx < 6:
            value = 12.0
        else:
            value = 30.0
        rows.append({"日期": day, **{hour: value for hour in range(24)}})
    daily = pd.DataFrame(rows)
    mapping = pd.DataFrame(
        {
            "日期": dates,
            "组合模型编号": ["(1,1)"] * 4 + ["(1,2)"] * 2 + ["(2,1)"] * 4,
            "组合模型名称": ["工作日-高负荷期"] * 4 + ["工作日-低负荷期"] * 2 + ["休息日-高负荷期"] * 4,
            "最终周内类别编码": [1] * 6 + [2] * 4,
            "年类编码": [1] * 4 + [2] * 2 + [1] * 4,
            "参与典型曲线建模": [True, True, True, False, True, True, True, True, True, True],
        }
    )

    merged = mod.merge_sparse_combo_models(daily, mapping, min_sample_days=3)

    sparse_rows = merged[merged["原始组合模型编号"] == "(1,2)"]
    assert sparse_rows["组合模型编号"].eq("(1,1)").all()
    assert sparse_rows["组合合并说明"].ne("未合并").all()

    summary, curves = mod.build_model_library(daily, merged)
    target_summary = summary[summary["组合模型编号"] == "(1,1)"].iloc[0]
    target_curve = curves[curves["组合模型编号"] == "(1,1)"].iloc[0]
    assert int(target_summary["年度权重天数"]) == 6
    assert int(target_summary["曲线建模天数"]) == 5
    assert np.isclose(float(target_curve["00:00"]), 10.8)


def test_industrial_runtime_model_library_preserves_weight_columns() -> None:
    from services.build_runtime_industrial import build_runtime_model_library  # noqa: PLC0415

    library_df = pd.DataFrame(
        [{
            "external_model_id": "(1,1)",
            "model_name": "工作日-高负荷期",
            "model_weight_days": 12,
            "model_weight_ratio": 12 / 365,
            "curve_sample_days": 10,
            **{f"h{i:02d}": float(i) for i in range(24)},
        }]
    )

    out = build_runtime_model_library(library_df, {"(1,1)": 0})

    assert out.columns.tolist()[:6] == [
        "internal_model_id",
        "external_model_id",
        "model_name",
        "model_weight_days",
        "model_weight_ratio",
        "curve_sample_days",
    ]
    assert int(out.loc[0, "model_weight_days"]) == 12
