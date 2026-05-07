from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_write_json(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _dedupe_notes_in_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "notes" and isinstance(v, list):
                deduped = []
                for item in v:
                    if item not in deduped:
                        deduped.append(item)
                out[k] = deduped
            else:
                out[k] = _dedupe_notes_in_obj(v)
        return out
    if isinstance(obj, list):
        return [_dedupe_notes_in_obj(v) for v in obj]
    return obj


def _resolve_case_name(
    output_dir: Path,
    case_name: str | None = None,
    opt_case: Any | None = None,
) -> str:
    if case_name:
        return str(case_name)

    if opt_case is not None:
        for name in ("case_name", "scenario_name", "internal_model_id"):
            value = getattr(opt_case, name, None)
            if value:
                return str(value)

        registry_scenario = getattr(opt_case, "registry_scenario", None)
        if registry_scenario is not None:
            for name in ("scenario_name", "internal_model_id"):
                value = getattr(registry_scenario, name, None)
                if value:
                    return str(value)

    return output_dir.name


def export_optimization_run(
    output_dir: str | Path,
    run_result,
    case_name: str | None = None,
    enable_plots: bool = True,
    opt_case: Any | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    if "enable_plot" in kwargs:
        enable_plots = bool(kwargs.pop("enable_plot"))
    if "plot" in kwargs:
        enable_plots = bool(kwargs.pop("plot"))
    if "case_label" in kwargs and not case_name:
        case_name = str(kwargs.pop("case_label"))
    if "generate_plots" in kwargs:
        enable_plots = bool(kwargs.pop("generate_plots"))
    if "opt_case" in kwargs and opt_case is None:
        opt_case = kwargs.pop("opt_case")

    out_dir = _ensure_dir(output_dir)
    case_name = _resolve_case_name(out_dir, case_name=case_name, opt_case=opt_case)

    import pandas as pd
    from storage_engine_project.optimization.optimizer_bridge import OptimizerBridge

    archive_df = OptimizerBridge.results_to_dataframe(run_result.archive_results)
    pop_df = OptimizerBridge.results_to_dataframe(run_result.population_results)
    history_df = pd.DataFrame(run_result.history)

    archive_path = out_dir / "archive_results.csv"
    population_path = out_dir / "population_results.csv"
    history_path = out_dir / "optimization_history.csv"

    archive_df.to_csv(archive_path, index=False, encoding="utf-8-sig")
    pop_df.to_csv(population_path, index=False, encoding="utf-8-sig")
    history_df.to_csv(history_path, index=False, encoding="utf-8-sig")

    best_result_path = out_dir / "best_result_summary.json"
    best_annual_summary_path = out_dir / "best_annual_summary.csv"
    best_financial_summary_path = out_dir / "best_financial_summary.csv"
    best_cashflow_table_path = out_dir / "best_cashflow_table.csv"
    best_monthly_summary_path = out_dir / "best_monthly_summary.csv"
    best_hourly_path = out_dir / "best_annual_hourly_operation.csv"

    plot_paths: list[str] = []
    plot_error: str | None = None

    if run_result.best_result is not None:
        best_summary = _dedupe_notes_in_obj(run_result.best_result.summary_dict())
        _safe_write_json(best_result_path, best_summary)

        ann = run_result.best_result.annual_operation_result
        fin = run_result.best_result.lifecycle_financial_result

        if ann is not None:
            pd.DataFrame([ann.summary_dict()]).to_csv(
                best_annual_summary_path, index=False, encoding="utf-8-sig"
            )
            ann.monthly_summary_dataframe().to_csv(
                best_monthly_summary_path, index=False, encoding="utf-8-sig"
            )

            hourly_rows = []
            for d in range(365):
                for h in range(24):
                    hourly_rows.append(
                        {
                            "day_index": d + 1,
                            "hour": h,
                            "baseline_net_load_kw": ann.baseline_net_load_kw[d, h],
                            "actual_net_load_kw": ann.actual_net_load_kw[d, h],
                            "grid_exchange_kw": ann.grid_exchange_kw[d, h],
                            "plan_charge_kw": ann.plan_charge_kw[d, h],
                            "plan_discharge_kw": ann.plan_discharge_kw[d, h],
                            "plan_service_kw": ann.plan_service_kw[d, h],
                            "exec_charge_kw": ann.exec_charge_kw[d, h],
                            "exec_discharge_kw": ann.exec_discharge_kw[d, h],
                            "exec_service_kw": ann.exec_service_kw[d, h],
                            "tariff_yuan_per_kwh": ann.tariff_yuan_per_kwh[d, h],
                            "arbitrage_revenue_yuan": ann.arbitrage_revenue_yuan[d, h],
                            "service_capacity_revenue_yuan": ann.service_capacity_revenue_yuan[d, h],
                            "service_delivery_revenue_yuan": ann.service_delivery_revenue_yuan[d, h],
                            "service_penalty_yuan": ann.service_penalty_yuan[d, h],
                            "degradation_cost_yuan": ann.degradation_cost_yuan[d, h],
                            "transformer_penalty_yuan": ann.transformer_penalty_yuan[d, h],
                            "voltage_penalty_yuan": ann.voltage_penalty_yuan[d, h],
                            "transformer_slack_kw": ann.transformer_slack_kw[d, h],
                            "soc_open": ann.soc_hourly_path[d, h],
                            "soc_close": ann.soc_hourly_path[d, h + 1],
                        }
                    )
            pd.DataFrame(hourly_rows).to_csv(best_hourly_path, index=False, encoding="utf-8-sig")

        if fin is not None:
            fin_summary = _dedupe_notes_in_obj(fin.summary_dict())
            pd.DataFrame([fin_summary]).to_csv(
                best_financial_summary_path, index=False, encoding="utf-8-sig"
            )
            fin.cashflow_dataframe().to_csv(best_cashflow_table_path, index=False, encoding="utf-8-sig")

        if enable_plots:
            try:
                from storage_engine_project.visualization.plot_dispatch import plot_dispatch_profiles
                from storage_engine_project.visualization.plot_economics import plot_financial_diagnostics
                from storage_engine_project.visualization.plot_pareto import plot_pareto_front
                from storage_engine_project.visualization.plot_scheme import plot_scheme_overview

                fig_root = _ensure_dir(out_dir / "figures")
                plot_paths.extend(plot_pareto_front(case_name=case_name, run_result=run_result, output_dir=fig_root / "optimization"))
                plot_paths.extend(plot_scheme_overview(case_name=case_name, best_result=run_result.best_result, output_dir=fig_root / "scheme"))
                if ann is not None:
                    plot_paths.extend(plot_dispatch_profiles(case_name=case_name, annual_result=ann, output_dir=fig_root / "dispatch"))
                if fin is not None:
                    plot_paths.extend(plot_financial_diagnostics(case_name=case_name, financial_result=fin, output_dir=fig_root / "economics"))
            except Exception as exc:
                plot_error = f"{type(exc).__name__}: {exc}"

    meta = {
        "archive_size": len(run_result.archive_results),
        "population_size": len(run_result.population_results),
        "all_evaluation_count": run_result.all_evaluation_count,
        "plot_count": len(plot_paths),
        "plot_error": plot_error,
    }
    _safe_write_json(out_dir / "run_meta.json", meta)

    if plot_paths:
        import pandas as pd
        pd.DataFrame({"plot_path": plot_paths}).to_csv(out_dir / "generated_plots.csv", index=False, encoding="utf-8-sig")

    out: dict[str, str] = {
        "archive_results": str(archive_path),
        "population_results": str(population_path),
        "history": str(history_path),
        "best_result_summary": str(best_result_path),
        "run_meta": str(out_dir / "run_meta.json"),
    }
    if run_result.best_result is not None:
        out.update(
            {
                "best_annual_summary": str(best_annual_summary_path),
                "best_financial_summary": str(best_financial_summary_path),
                "best_cashflow_table": str(best_cashflow_table_path),
                "best_monthly_summary": str(best_monthly_summary_path),
                "best_annual_hourly_operation": str(best_hourly_path),
            }
        )
    if plot_paths:
        out["generated_plots"] = str(out_dir / "generated_plots.csv")

    return out
