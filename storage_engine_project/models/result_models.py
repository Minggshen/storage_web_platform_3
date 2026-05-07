from __future__ import annotations

"""
统一结果模型入口。

作用：
1. 保持你原工程里 models.result_models 的导入口径不变；
2. 把新五层用到的结果对象统一重新导出；
3. 避免后续 visualization / analysis / main / optimizer 中出现导入分裂。
"""

from storage_engine_project.economics.economic_result_models import (
    AnnualRevenueAuditResult,
    CapitalCostBreakdown,
    LifecycleCashflowTable,
    LifecycleFinancialResult,
)
from storage_engine_project.optimization.optimization_models import (
    ConstraintVector,
    FitnessEvaluationResult,
    ObjectiveVector,
    ScreeningResult,
    StorageDecision,
)
from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationResult
from storage_engine_project.simulation.dispatch_result_models import (
    DayAheadDispatchPlan,
    DayAheadObjectiveBreakdown,
)
from storage_engine_project.simulation.rolling_dispatch import RollingDispatchResult

__all__ = [
    # 第二层
    "DayAheadObjectiveBreakdown",
    "DayAheadDispatchPlan",
    # 第三层
    "RollingDispatchResult",
    "AnnualOperationResult",
    # 第四层
    "CapitalCostBreakdown",
    "AnnualRevenueAuditResult",
    "LifecycleCashflowTable",
    "LifecycleFinancialResult",
    # 第五层
    "StorageDecision",
    "ScreeningResult",
    "ObjectiveVector",
    "ConstraintVector",
    "FitnessEvaluationResult",
]