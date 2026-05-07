from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from models.project_model import DeviceRecord
else:
    DeviceRecord = Any


@dataclass(slots=True)
class SearchSpaceInferenceResult:
    search_power_min_kw: float
    device_power_max_kw: float
    search_duration_min_h: float
    search_duration_max_h: float
    transformer_limit_kw: float | None
    peak_kw: float | None
    valley_kw: float | None
    annual_mean_kw: float | None
    mean_daily_energy_kwh: float | None
    source: str
    basis: list[str]
    notes: list[str]
    explain: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SearchSpaceInferenceService:
    """Infer legacy solver search-space fields from transformer constraints, runtime statistics and device-library priors."""

    def infer(
        self,
        *,
        node_params: dict[str, Any],
        runtime_stats: dict[str, Any] | None,
        device_records: Iterable[DeviceRecord | dict[str, Any]],
        transformer_capacity_kva: float | None,
        transformer_pf_limit: float | None,
        transformer_reserve_ratio: float | None,
        grid_interconnection_limit_kw: float | None,
    ) -> SearchSpaceInferenceResult:
        runtime_stats = dict(runtime_stats or {})
        peak_kw = self._safe_float(runtime_stats.get('peak_kw'), None)
        valley_kw = self._safe_float(runtime_stats.get('valley_kw'), None)
        annual_mean_kw = self._safe_float(runtime_stats.get('annual_mean_kw'), None)
        mean_daily_energy_kwh = self._safe_float(runtime_stats.get('mean_daily_energy_kwh'), None)

        # 注意：功率、容量、时长的搜索范围始终由电网/负荷/设备库自动推断，
        # 不再读取 node_params 中的用户显式覆盖（用户难以判断合理范围）。
        durations = self._candidate_durations(device_records)
        duration_min_default = min(durations) if durations else 2.0
        duration_max_default = max(durations) if durations else 4.0

        transformer_limit_kw = None
        if None not in (transformer_capacity_kva, transformer_pf_limit, transformer_reserve_ratio):
            transformer_limit_kw = float(transformer_capacity_kva) * float(transformer_pf_limit) * max(0.0, 1.0 - float(transformer_reserve_ratio))

        notes: list[str] = []
        basis: list[str] = []
        source_parts: list[str] = []
        allow_grid_export = self._first_bool(
            node_params,
            ["allow_grid_export", "allow_reverse_power_to_grid", "allow_export_to_grid"],
            False,
        )

        # Power upper bound —— 始终由电网信息推断
        upper_candidates: list[dict[str, Any]] = []
        if peak_kw is not None and peak_kw > 0:
            upper_candidates.append({
                "constraint": "runtime_peak",
                "label": "负荷峰值",
                "source": "runtime_stats",
                "value": float(peak_kw),
                "unit": "kW",
            })
            source_parts.append('runtime_peak')
            basis.append(f'功率上界候选：负荷峰值 {peak_kw:.2f} kW。')
        if transformer_limit_kw is not None and transformer_limit_kw > 0:
            upper_candidates.append({
                "constraint": "transformer_limit",
                "label": "配变可用容量",
                "source": "topology_transformer",
                "value": float(transformer_limit_kw),
                "unit": "kW",
            })
            source_parts.append('transformer_limit')
            basis.append(
                '功率上界候选：配变可用容量 '
                f'{transformer_limit_kw:.2f} kW = {float(transformer_capacity_kva):.2f} kVA '
                f'× {float(transformer_pf_limit):.3f} × (1 - {float(transformer_reserve_ratio):.3f})。'
            )
        if grid_interconnection_limit_kw is not None and grid_interconnection_limit_kw > 0:
            upper_candidates.append({
                "constraint": "grid_limit",
                "label": "并网功率限制",
                "source": "interconnection_limit",
                "value": float(grid_interconnection_limit_kw),
                "unit": "kW",
            })
            source_parts.append('grid_limit')
            basis.append(f'功率上界候选：并网功率限制 {float(grid_interconnection_limit_kw):.2f} kW。')
        if upper_candidates:
            upper_decisive = min(upper_candidates, key=lambda item: float(item["value"]))
            power_upper = float(upper_decisive["value"])
            basis.append(f'最终功率上界取上述候选最小值：{power_upper:.2f} kW。')
        else:
            power_upper = 500.0
            upper_decisive = {
                "constraint": "default_power_upper",
                "label": "默认功率上界",
                "source": "service_default",
                "value": power_upper,
                "unit": "kW",
            }
            upper_candidates.append(upper_decisive)
            source_parts.append('default_power_upper')
            notes.append('缺少 runtime 峰值与变压器限制信息，功率上界退回默认 500 kW。')
            basis.append('功率上界：缺少负荷/配变/并网约束数据，临时采用默认 500 kW。')

        # Power lower bound —— 始终由负荷统计量推断
        if peak_kw is not None and peak_kw > 0:
            lower_candidates = [
                {
                    "constraint": "minimum_floor",
                    "label": "最小搜索功率",
                    "source": "service_default",
                    "value": 30.0,
                    "unit": "kW",
                },
                {
                    "constraint": "power_upper_ratio",
                    "label": "功率上界 15%",
                    "source": "derived",
                    "value": 0.15 * float(power_upper),
                    "unit": "kW",
                },
                {
                    "constraint": "runtime_peak_ratio",
                    "label": "负荷峰值 5%",
                    "source": "runtime_stats",
                    "value": 0.05 * float(peak_kw),
                    "unit": "kW",
                },
            ]
            soft_cap = min(lower_candidates[1:], key=lambda item: float(item["value"]))
            power_min = max(30.0, float(soft_cap["value"]))
            lower_decisive = lower_candidates[0] if power_min == 30.0 else soft_cap
            source_parts.append('runtime_peak_min_ratio')
            basis.append(
                f'功率下界：max(30 kW, min(功率上界 15%, 负荷峰值 5%)) = {power_min:.2f} kW。'
            )
        elif annual_mean_kw is not None and annual_mean_kw > 0:
            lower_candidates = [
                {
                    "constraint": "minimum_floor",
                    "label": "最小搜索功率",
                    "source": "service_default",
                    "value": 30.0,
                    "unit": "kW",
                },
                {
                    "constraint": "power_upper_ratio",
                    "label": "功率上界 15%",
                    "source": "derived",
                    "value": 0.15 * float(power_upper),
                    "unit": "kW",
                },
                {
                    "constraint": "runtime_mean_ratio",
                    "label": "年平均负荷 12%",
                    "source": "runtime_stats",
                    "value": 0.12 * float(annual_mean_kw),
                    "unit": "kW",
                },
            ]
            soft_cap = min(lower_candidates[1:], key=lambda item: float(item["value"]))
            power_min = max(30.0, float(soft_cap["value"]))
            lower_decisive = lower_candidates[0] if power_min == 30.0 else soft_cap
            source_parts.append('runtime_mean_min_ratio')
            basis.append(
                f'功率下界：max(30 kW, min(功率上界 15%, 年平均负荷 12%)) = {power_min:.2f} kW。'
            )
        else:
            power_min = max(30.0, 0.1 * float(power_upper))
            lower_candidates = [
                {
                    "constraint": "minimum_floor",
                    "label": "最小搜索功率",
                    "source": "service_default",
                    "value": 30.0,
                    "unit": "kW",
                },
                {
                    "constraint": "default_power_min_ratio",
                    "label": "功率上界 10%",
                    "source": "service_default",
                    "value": 0.1 * float(power_upper),
                    "unit": "kW",
                },
            ]
            lower_decisive = lower_candidates[0] if power_min == 30.0 else lower_candidates[1]
            source_parts.append('default_power_min_ratio')
            notes.append('缺少负荷统计量，功率下界按功率上界比例兜底。')
            basis.append(f'功率下界：缺少负荷统计量，按功率上界 10% 且不低于 30 kW 兜底，结果 {power_min:.2f} kW。')

        if float(power_upper) < float(power_min):
            upper_decisive = {
                "constraint": "search_power_min_kw",
                "label": "功率下限保护",
                "source": "derived",
                "value": float(power_min),
                "unit": "kW",
            }
            upper_candidates.append(upper_decisive)
        power_upper = max(float(power_upper), float(power_min))
        if allow_grid_export:
            basis.append('反送电约束：当前负荷允许向上级电网反送，最终调度不额外按目标负荷峰值收紧容量。')
        else:
            basis.append('反送电约束：当前负荷不允许向上级电网反送，求解器最终配置边界会按目标负荷峰值和日最大用电量/SOC 窗口收紧。')
        basis.append('线路/电压约束：不使用经验公式直接压缩前端搜索范围；候选方案会在求解器中调用 OpenDSS 逐时潮流校核，并在健康检查和配电网影响报告中追踪越限。')

        # Duration bounds —— 始终由设备库时长 + 负荷锚点推断
        duration_min = float(duration_min_default)
        duration_min_candidates = [
            {
                "constraint": "minimum_duration_floor",
                "label": "最小时长保护",
                "source": "service_default",
                "value": 0.5,
                "unit": "h",
            },
            {
                "constraint": "device_duration_min",
                "label": "设备库最小时长",
                "source": "device_library",
                "value": float(duration_min_default),
                "unit": "h",
            },
        ]
        source_parts.append('device_duration_min')
        basis.append(f'时长下界：来自设备库可用设备最小时长 {duration_min:.2f} h。')

        duration_max = float(duration_max_default)
        duration_max_candidates = [
            {
                "constraint": "device_duration_max",
                "label": "设备库最大时长",
                "source": "device_library",
                "value": float(duration_max_default),
                "unit": "h",
            }
        ]
        source_parts.append('device_duration_max')
        basis.append(f'时长上界候选：来自设备库可用设备最大时长 {duration_max:.2f} h。')
        # load-informed adjustment: use daily energy divided by peak as a soft duration anchor
        if mean_daily_energy_kwh is not None and peak_kw is not None and peak_kw > 0:
            load_anchor = max(2.0, min(8.0, 0.8 * float(mean_daily_energy_kwh) / max(float(peak_kw), 1e-9)))
            duration_max_candidates.append({
                "constraint": "runtime_daily_energy_anchor",
                "label": "日均电量/峰值锚点",
                "source": "runtime_stats",
                "value": float(load_anchor),
                "unit": "h",
            })
            duration_max = max(duration_max, load_anchor)
            source_parts.append('runtime_daily_energy_anchor')
            basis.append(
                f'时长上界候选：按日均电量/峰值负荷得到负荷锚点 {load_anchor:.2f} h，最终取更大值。'
            )
        elif annual_mean_kw is not None and annual_mean_kw > 0:
            load_anchor = max(2.0, min(6.0, float(power_upper) / max(float(annual_mean_kw), 1e-9)))
            duration_max_candidates.append({
                "constraint": "runtime_mean_anchor",
                "label": "功率上界/年平均负荷锚点",
                "source": "runtime_stats",
                "value": float(load_anchor),
                "unit": "h",
            })
            duration_max = max(duration_max, load_anchor)
            source_parts.append('runtime_mean_anchor')
            basis.append(
                f'时长上界候选：按功率上界/年平均负荷得到负荷锚点 {load_anchor:.2f} h，最终取更大值。'
            )

        duration_min = max(0.5, float(duration_min))
        duration_min_decisive = max(duration_min_candidates, key=lambda item: float(item["value"]))
        duration_max = max(float(duration_min), float(duration_max))
        duration_max_candidates.append({
            "constraint": "search_duration_min_h",
            "label": "时长下限保护",
            "source": "derived",
            "value": float(duration_min),
            "unit": "h",
        })
        duration_max_decisive = max(duration_max_candidates, key=lambda item: float(item["value"]))

        def build_explain_item(
            boundary: str,
            name: str,
            final_value: float,
            unit: str,
            decisive: dict[str, Any],
            candidates: list[dict[str, Any]],
            description: str,
        ) -> dict[str, Any]:
            decisive_constraint = str(decisive.get("constraint") or "")
            normalized_candidates = []
            for candidate in candidates:
                candidate_value = candidate.get("value")
                normalized_candidates.append({
                    **candidate,
                    "value": None if candidate_value is None else round(float(candidate_value), 4),
                    "is_decisive": str(candidate.get("constraint") or "") == decisive_constraint,
                })
            return {
                "boundary": boundary,
                "boundary_name": name,
                "unit": unit,
                "final_value": round(float(final_value), 4),
                "decisive_constraint": decisive_constraint,
                "decisive_label": decisive.get("label"),
                "candidate_constraints": normalized_candidates,
                "description": description,
            }

        explain = [
            build_explain_item(
                "device_power_max_kw",
                "设备功率上限",
                power_upper,
                "kW",
                upper_decisive,
                upper_candidates,
                "功率上限取负荷峰值、配变可用容量、并网功率限制等候选值中的最小约束；若缺少数据则使用默认上界。",
            ),
            build_explain_item(
                "search_power_min_kw",
                "GA 搜索功率下限",
                power_min,
                "kW",
                lower_decisive,
                lower_candidates,
                "功率下限由最小搜索功率保护与负荷统计比例共同决定，避免搜索空间过窄或过小。",
            ),
            build_explain_item(
                "search_duration_min_h",
                "GA 搜索时长下限",
                duration_min,
                "h",
                duration_min_decisive,
                duration_min_candidates,
                "时长下限来自设备库可用设备最小时长，并受服务默认最小时长保护。",
            ),
            build_explain_item(
                "search_duration_max_h",
                "GA 搜索时长上限",
                duration_max,
                "h",
                duration_max_decisive,
                duration_max_candidates,
                "时长上限取设备库最大时长、负荷运行锚点和时长下限保护中的最大值。",
            ),
        ]

        source = '+'.join(dict.fromkeys(source_parts)) if source_parts else 'unknown'
        return SearchSpaceInferenceResult(
            search_power_min_kw=round(float(power_min), 4),
            device_power_max_kw=round(float(power_upper), 4),
            search_duration_min_h=round(float(duration_min), 4),
            search_duration_max_h=round(float(duration_max), 4),
            transformer_limit_kw=None if transformer_limit_kw is None else round(float(transformer_limit_kw), 4),
            peak_kw=None if peak_kw is None else round(float(peak_kw), 4),
            valley_kw=None if valley_kw is None else round(float(valley_kw), 4),
            annual_mean_kw=None if annual_mean_kw is None else round(float(annual_mean_kw), 4),
            mean_daily_energy_kwh=None if mean_daily_energy_kwh is None else round(float(mean_daily_energy_kwh), 4),
            source=source,
            basis=basis,
            notes=notes,
            explain=explain,
        )

    def _candidate_durations(self, device_records: Iterable[DeviceRecord | dict[str, Any]]) -> list[float]:
        vals: list[float] = []
        for rec in device_records:
            if not self._safe_bool(self._record_value(rec, 'enabled', True), True):
                continue
            duration = self._safe_float(self._record_value(rec, 'duration_hour'), None)
            if duration is None:
                p = self._safe_float(self._record_value(rec, 'rated_power_kw'), None)
                e = self._safe_float(self._record_value(rec, 'rated_energy_kwh'), None)
                if p not in (None, 0) and e not in (None, 0):
                    duration = float(e) / float(p)
            if duration is not None and duration > 0:
                vals.append(float(duration))
        return sorted(vals)

    def _record_value(self, record: DeviceRecord | dict[str, Any], key: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(key, default)
        return getattr(record, key, default)

    def _first_float(self, mapping: dict[str, Any], keys: list[str]) -> float | None:
        for k in keys:
            v = self._safe_float(mapping.get(k), None)
            if v is not None:
                return v
        return None

    def _first_bool(self, mapping: dict[str, Any], keys: list[str], default: bool) -> bool:
        for k in keys:
            if k not in mapping:
                continue
            value = mapping.get(k)
            if value in (None, ''):
                continue
            return self._safe_bool(value, default)
        return bool(default)

    def _safe_float(self, value: Any, default: float | None) -> float | None:
        if value in (None, ''):
            return default
        try:
            return float(value)
        except Exception:
            return default

    def _safe_bool(self, value: Any, default: bool) -> bool:
        if value in (None, ''):
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(int(value))
        text = str(value).strip().lower()
        if text in {'1', 'true', 'yes', 'y', 'on', '是', '启用'}:
            return True
        if text in {'0', 'false', 'no', 'n', 'off', '否', '停用'}:
            return False
        return bool(default)
