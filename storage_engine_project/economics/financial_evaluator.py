from __future__ import annotations

"""
兼容入口：把你原工程 economics.financial_evaluator 的调用，
切换到第四层生命周期财务评价器。

推荐使用：
    evaluate_financials(...)
"""

from dataclasses import dataclass

from storage_engine_project.data.annual_context_builder import AnnualOperationContext
from storage_engine_project.economics.lifecycle_financial_evaluator import (
    LifecycleFinancialConfig,
    LifecycleFinancialEvaluator,
)
from storage_engine_project.economics.economic_result_models import LifecycleFinancialResult
from storage_engine_project.simulation.annual_operation_kernel import AnnualOperationResult


@dataclass(slots=True)
class FinancialEvaluationInput:
    ctx: AnnualOperationContext
    annual_result: AnnualOperationResult
    config: LifecycleFinancialConfig | None = None


class FinancialEvaluator:
    def __init__(self, config: LifecycleFinancialConfig | None = None) -> None:
        self.evaluator = LifecycleFinancialEvaluator(config=config)

    def evaluate(self, fin_input: FinancialEvaluationInput) -> LifecycleFinancialResult:
        return self.evaluator.evaluate(
            ctx=fin_input.ctx,
            annual_result=fin_input.annual_result,
        )


def evaluate_financials(
    ctx: AnnualOperationContext,
    annual_result: AnnualOperationResult,
    config: LifecycleFinancialConfig | None = None,
) -> LifecycleFinancialResult:
    evaluator = FinancialEvaluator(config=config)
    return evaluator.evaluate(
        FinancialEvaluationInput(
            ctx=ctx,
            annual_result=annual_result,
            config=config,
        )
    )