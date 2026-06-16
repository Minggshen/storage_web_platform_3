from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

DEFAULT_DEVICE_SAFETY_WEIGHTS: dict[str, float] = {
    "cell": 0.12,
    "capacity": 0.05,
    "thermal": 0.14,
    "temp_range": 0.04,
    "detection": 0.10,
    "fire_suppression": 0.12,
    "explosion": 0.10,
    "bms": 0.12,
    "propagation": 0.08,
    "ip": 0.05,
    "corrosion": 0.03,
    "certification": 0.05,
}


@dataclass(slots=True)
class DeviceSafetyRule:
    dimension: str
    source_column: str
    pattern: str
    score: float
    priority: int
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.dimension}|{self.source_column}|{self.pattern}|{self.priority}|{self.score}"


@dataclass(slots=True)
class DeviceSafetyConfig:
    weights: dict[str, float]
    rules: list[DeviceSafetyRule]
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def dimensions(self) -> list[str]:
        ordered = list(self.weights.keys())
        for rule in self.rules:
            if rule.dimension and rule.dimension not in ordered:
                ordered.append(rule.dimension)
        return ordered


@dataclass(slots=True)
class DeviceSafetyScores:
    sub_scores: dict[str, float]
    weighted_score: float
    device_safety_cost: float
    trace: dict[str, list[str]]
    data_quality_flags: list[str]


def has_device_safety_sheets(path: str | Path) -> bool:
    try:
        xl = pd.ExcelFile(path)
    except Exception:
        return False
    return {"安全权重", "安全评分规则"}.issubset(set(xl.sheet_names))


def read_device_safety_config(path: str | Path) -> DeviceSafetyConfig:
    xl = pd.ExcelFile(path)
    missing = {"安全权重", "安全评分规则"} - set(xl.sheet_names)
    if missing:
        raise ValueError(f"设备策略库缺少设备安全评分 Sheet：{', '.join(sorted(missing))}")

    weights_df = pd.read_excel(xl, sheet_name="安全权重")
    rules_df = pd.read_excel(xl, sheet_name="安全评分规则")
    weights, labels = _parse_weights(weights_df)
    rules = _parse_rules(rules_df)
    if not rules:
        raise ValueError("Sheet 安全评分规则 未解析出任何规则。")
    return DeviceSafetyConfig(weights=weights, rules=rules, labels=labels)


def compute_device_safety_cost(
    sub_scores: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> float:
    normalized = normalize_device_safety_weights(weights, dimensions=sub_scores.keys())
    raw = 0.0
    for dim, score in sub_scores.items():
        raw += max(0.0, min(100.0, _safe_float(score, 0.0))) / 100.0 * normalized.get(dim, 0.0)
    return max(0.0, min(1.0, 1.0 - raw))


def normalize_device_safety_weights(
    weights: Mapping[str, float] | None,
    *,
    dimensions: Iterable[str] | None = None,
) -> dict[str, float]:
    ordered = [str(dim).strip() for dim in (dimensions or DEFAULT_DEVICE_SAFETY_WEIGHTS.keys()) if str(dim).strip()]
    if not ordered:
        return {}

    values: dict[str, float] = {}
    for dim in ordered:
        default = DEFAULT_DEVICE_SAFETY_WEIGHTS.get(dim, 1.0)
        raw = (weights or {}).get(dim, default)
        value = _safe_float(raw, default)
        values[dim] = max(0.0, value) if np.isfinite(value) else 0.0

    total = sum(values.values())
    if total <= 1e-12:
        equal = 1.0 / len(ordered)
        return {dim: equal for dim in ordered}
    return {dim: value / total for dim, value in values.items()}


def score_device(
    row: Mapping[str, Any],
    config: DeviceSafetyConfig,
    *,
    usage_counts: dict[str, int] | None = None,
) -> DeviceSafetyScores:
    rules_by_dim: dict[str, list[DeviceSafetyRule]] = {}
    for rule in config.rules:
        rules_by_dim.setdefault(rule.dimension, []).append(rule)

    sub_scores: dict[str, float] = {}
    trace: dict[str, list[str]] = {}
    flags: list[str] = []

    for dim in config.dimensions:
        rules = sorted(rules_by_dim.get(dim, []), key=_rule_sort_key, reverse=True)
        non_default = [rule for rule in rules if rule.priority > 0]
        defaults = [rule for rule in rules if rule.priority <= 0]
        has_disclosed_value = any(not _is_blank(_source_value(row, rule.source_column, dim)) for rule in non_default)
        if not has_disclosed_value:
            flags.append(f"{dim}_not_disclosed")

        if dim == "certification":
            score, notes, matched_keys, used_default = _score_certification(row, non_default, defaults)
        else:
            score, notes, matched_keys, used_default = _score_first_match(row, dim, non_default, defaults)

        if used_default:
            flags.append(f"{dim}_defaulted")
        if usage_counts is not None:
            for key in matched_keys:
                usage_counts[key] = usage_counts.get(key, 0) + 1

        sub_scores[dim] = max(0.0, min(100.0, float(score)))
        trace[dim] = notes

    weighted_cost = compute_device_safety_cost(sub_scores, config.weights)
    weighted_score = (1.0 - weighted_cost) * 100.0
    return DeviceSafetyScores(
        sub_scores=sub_scores,
        weighted_score=weighted_score,
        device_safety_cost=weighted_cost,
        trace=trace,
        data_quality_flags=_dedupe(flags),
    )


def score_device_library(
    rows: Iterable[Mapping[str, Any]],
    config: DeviceSafetyConfig,
) -> tuple[list[DeviceSafetyScores], list[str]]:
    rule_counts = {rule.key: 0 for rule in config.rules if rule.priority > 0}
    row_list = list(rows)
    scores = [score_device(row, config, usage_counts=rule_counts) for row in row_list]

    rules_by_key = {rule.key: rule for rule in config.rules}
    never_matched_flags: list[str] = []
    for key, count in rule_counts.items():
        if count > 0:
            continue
        rule = rules_by_key[key]
        token = _flag_token(rule.pattern or rule.note or rule.source_column)
        never_matched_flags.append(f"{rule.dimension}_rule_{token}_never_matched")

    return scores, never_matched_flags


def _parse_weights(df: pd.DataFrame) -> tuple[dict[str, float], dict[str, str]]:
    weights: dict[str, float] = {}
    labels: dict[str, str] = {}
    for _, row in df.iterrows():
        dim = str(row.get("dimension", "")).strip()
        if not dim:
            continue
        weights[dim] = _safe_float(row.get("default_weight"), DEFAULT_DEVICE_SAFETY_WEIGHTS.get(dim, 0.0))
        labels[dim] = str(row.get("label_zh", "")).strip()
    return normalize_device_safety_weights(weights), labels


def _parse_rules(df: pd.DataFrame) -> list[DeviceSafetyRule]:
    rules: list[DeviceSafetyRule] = []
    for _, row in df.iterrows():
        dim = str(row.get("dimension", "")).strip()
        source = str(row.get("source_column", "")).strip()
        if not dim or not source:
            continue
        pattern_raw = row.get("pattern", "")
        pattern = "" if _is_blank(pattern_raw) else str(pattern_raw).strip()
        priority = int(round(_safe_float(row.get("priority"), 0.0)))
        score = max(0.0, min(100.0, _safe_float(row.get("score"), 0.0)))
        note = str(row.get("note", "")).strip()
        if pattern and not _is_threshold_pattern(pattern):
            re.compile(pattern)
        rules.append(
            DeviceSafetyRule(
                dimension=dim,
                source_column=source,
                pattern=pattern,
                score=score,
                priority=priority,
                note=note,
            )
        )
    return rules


def _score_first_match(
    row: Mapping[str, Any],
    dim: str,
    rules: list[DeviceSafetyRule],
    defaults: list[DeviceSafetyRule],
) -> tuple[float, list[str], list[str], bool]:
    for rule in rules:
        value = _source_value(row, rule.source_column, dim)
        if _matches(value, rule.pattern, dim):
            return rule.score, [_rule_note(rule)], [rule.key], False
    default = defaults[0] if defaults else None
    if default is None:
        return 0.0, [f"{dim} 未配置默认评分规则"], [], True
    return default.score, [_rule_note(default)], [], True


def _score_certification(
    row: Mapping[str, Any],
    rules: list[DeviceSafetyRule],
    defaults: list[DeviceSafetyRule],
) -> tuple[float, list[str], list[str], bool]:
    total = 0.0
    notes: list[str] = []
    matched_keys: list[str] = []
    for rule in rules:
        value = _source_value(row, rule.source_column, "certification")
        if _matches(value, rule.pattern, "certification"):
            total += float(rule.score)
            notes.append(_rule_note(rule))
            matched_keys.append(rule.key)
    if matched_keys:
        return min(100.0, total), notes, matched_keys, False
    default = defaults[0] if defaults else None
    if default is None:
        return 0.0, ["认证信息未披露，且未配置默认评分规则"], [], True
    return default.score, [_rule_note(default)], [], True


def _source_value(row: Mapping[str, Any], source_column: str, dim: str) -> Any:
    source = str(source_column or "").strip()
    if source == "operating_temp_range_c":
        low = _mapping_get(row, "operating_temp_min_c")
        high = _mapping_get(row, "operating_temp_max_c")
        if _is_blank(low) or _is_blank(high):
            return None
        return _safe_float(high) - _safe_float(low)
    return _mapping_get(row, source)


def _matches(value: Any, pattern: str, dim: str) -> bool:
    if _is_blank(value) or _is_blank(pattern):
        return False
    text = str(value).strip()
    pat = str(pattern).strip()
    if dim == "temp_range" or _is_threshold_pattern(pat):
        threshold_match = _threshold_match(_safe_float(value, np.nan), pat)
        if threshold_match is not None:
            return threshold_match
    return re.search(pat, text, flags=re.IGNORECASE) is not None


def _threshold_match(value: float, pattern: str) -> bool | None:
    if not np.isfinite(value):
        return False
    match = re.fullmatch(r"\s*(>=|<=|>|<)?\s*(-?\d+(?:\.\d+)?)\s*", str(pattern))
    if match is None:
        return None
    op = match.group(1) or ">="
    threshold = float(match.group(2))
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    return None


def _is_threshold_pattern(pattern: str) -> bool:
    return re.fullmatch(r"\s*(>=|<=|>|<)?\s*-?\d+(?:\.\d+)?\s*", str(pattern or "")) is not None


def _rule_sort_key(rule: DeviceSafetyRule) -> tuple[int, int]:
    pattern = "" if _is_blank(rule.pattern) else str(rule.pattern)
    return int(rule.priority), len(pattern)


def _mapping_get(row: Mapping[str, Any], key: str) -> Any:
    try:
        return row.get(key)  # type: ignore[union-attr]
    except AttributeError:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if _is_blank(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def _rule_note(rule: DeviceSafetyRule) -> str:
    if rule.note:
        return rule.note
    if rule.pattern:
        return f"{rule.source_column} 匹配 {rule.pattern}"
    return f"{rule.dimension} 默认评分"


def _flag_token(value: str) -> str:
    token = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", str(value)).strip("_")
    return token[:64] or "empty"


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
