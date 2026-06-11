from __future__ import annotations

import warnings
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

OUTPUT_ROOT_NAME = "按工休和年峰谷分析的1h级典型日负荷模型_改"

TARGET_FREQ = "1h"
POINTS_PER_DAY = 24

WEEK_CLUSTER_SIL_THRESHOLD = 0.12
WEEK_PROFILE_GAP_THRESHOLD = 0.05
WEEK_ENERGY_GAP_THRESHOLD = 0.04

SPECIAL_WEEK_SIL_THRESHOLD = 0.15

YEAR_LEVEL_COUNT = 5
YEAR_LEVEL_NAMES = {
    1: "高负荷期",
    2: "较高负荷期",
    3: "中负荷期",
    4: "较低负荷期",
    5: "低负荷期",
}

MIN_COMBO_SAMPLE_DAYS = 5
WEEK_QUALITY_MIN_DAYS = 5
WEEK_QUALITY_LOW_ENERGY_RATIO = 0.08
WEEK_QUALITY_HIGH_ENERGY_RATIO = 8.0
WEEK_QUALITY_SPIKE_TO_P95_RATIO = 8.0

RANDOM_STATE = 42

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FINAL_CAT_CODE_MAP = {
    "工作日": 1,
    "休息日": 2,
    "同类日": 3,
}

PATTERN_CHAR_MAP = {
    "工作日": "W",
    "休息日": "R",
    "同类日": "S",
}

PATTERN_CHAR_TO_NAME = {
    "W": "工作日",
    "R": "休息日",
    "S": "同类日",
}


def get_time_labels(points_per_day: int) -> list[str]:
    if points_per_day == 24:
        return [f"{h:02d}:00" for h in range(24)]
    elif points_per_day == 96:
        return [f"{i//4:02d}:{(i % 4) * 15:02d}" for i in range(96)]
    else:
        step_minutes = 24 * 60 // points_per_day
        labels = []
        for i in range(points_per_day):
            total_minutes = i * step_minutes
            hh = total_minutes // 60
            mm = total_minutes % 60
            labels.append(f"{hh:02d}:{mm:02d}")
        return labels


TIME_LABELS = get_time_labels(POINTS_PER_DAY)


def pattern_to_text(pattern: str) -> str:
    if pattern is None or pd.isna(pattern):
        return "无法识别"
    week_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    if pattern == "SSSSSSS":
        return "全周同类日"
    if "M" in pattern:
        return "不完整周"
    parts = []
    for i, ch in enumerate(pattern):
        parts.append(f"{week_names[i]}-{PATTERN_CHAR_TO_NAME.get(ch, '未知')}")
    return "；".join(parts)


def count_pattern_mismatch(a: str, b: str) -> int | None:
    if not a or not b:
        return None
    if len(a) != len(b):
        return None
    cnt = 0
    valid = 0
    for x, y in zip(a, b):
        if x == "M" or y == "M":
            continue
        valid += 1
        if x != y:
            cnt += 1
    if valid == 0:
        return None
    return cnt


def read_load_excel(file_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(file_path, sheet_name=0, header=None)
    if raw.shape[1] < 2:
        raise ValueError("Excel 至少需要两列：时间列、负荷列。")
    raw = raw.iloc[:, :2].copy()
    raw.columns = ["时间", "负荷"]
    first_time = pd.to_datetime(raw.iloc[0, 0], errors="coerce")
    first_load = pd.to_numeric(raw.iloc[0, 1], errors="coerce")
    if pd.isna(first_time) and pd.isna(first_load):
        raw = raw.iloc[1:].copy()
    raw["时间"] = pd.to_datetime(raw["时间"], errors="coerce")
    raw["负荷"] = pd.to_numeric(raw["负荷"], errors="coerce")
    raw = raw.dropna(subset=["时间", "负荷"])
    raw = raw.sort_values("时间")
    raw = raw.groupby("时间", as_index=False)["负荷"].mean()
    df = raw.set_index("时间").sort_index()
    inferred_freq = pd.infer_freq(df.index)
    if inferred_freq is None:
        inferred_freq = "15min"
    full_index = pd.date_range(df.index.min(), df.index.max(), freq=inferred_freq)
    df = df.reindex(full_index)
    df.index.name = "时间"
    df["负荷"] = df["负荷"].interpolate(method="time", limit_direction="both")
    df["负荷"] = df["负荷"].ffill().bfill()
    df_1h = df.resample(TARGET_FREQ).mean()
    df_1h["负荷"] = df_1h["负荷"].interpolate(method="time", limit_direction="both")
    df_1h["负荷"] = df_1h["负荷"].ffill().bfill()
    return df_1h.reset_index()


def build_daily_profiles(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["日期"] = df["时间"].dt.date
    df["时段序号"] = df["时间"].dt.hour
    df["星期序号"] = df["时间"].dt.weekday
    df["星期"] = df["星期序号"].map({
        0: "周一", 1: "周二", 2: "周三", 3: "周四",
        4: "周五", 5: "周六", 6: "周日"
    })
    df["周起始日"] = (
        df["时间"].dt.normalize() - pd.to_timedelta(df["时间"].dt.weekday, unit="D")
    ).dt.date
    pivot = df.pivot_table(index="日期", columns="时段序号", values="负荷", aggfunc="mean")
    pivot = pivot.reindex(columns=range(POINTS_PER_DAY))
    pivot = pivot.dropna(how="any")
    daily = pivot.reset_index()
    meta = df.groupby("日期").agg(
        星期序号=("星期序号", "first"),
        星期=("星期", "first"),
        周起始日=("周起始日", "first"),
    ).reset_index()
    daily = daily.merge(meta, on="日期", how="left")
    return daily, df


def _build_day_features(day_matrix: np.ndarray) -> np.ndarray:
    day_mean = day_matrix.mean(axis=1)
    day_peak = day_matrix.max(axis=1)
    day_valley = day_matrix.min(axis=1)
    day_std = day_matrix.std(axis=1)
    load_factor = np.divide(day_mean, day_peak, out=np.zeros_like(day_mean), where=day_peak != 0)
    shape_feature = np.divide(
        day_matrix,
        day_mean[:, None],
        out=np.zeros_like(day_matrix),
        where=day_mean[:, None] != 0
    )
    feature = np.concatenate(
        [
            shape_feature,
            day_mean[:, None],
            day_peak[:, None],
            day_valley[:, None],
            day_std[:, None],
            load_factor[:, None],
        ],
        axis=1,
    )
    return feature


def assess_week_data_quality(day_matrix: np.ndarray) -> dict:
    n_days = int(day_matrix.shape[0])
    reasons: list[str] = []
    daily_abnormal = np.zeros(n_days, dtype=bool)

    if n_days < WEEK_QUALITY_MIN_DAYS:
        reasons.append(f"有效天数少于{WEEK_QUALITY_MIN_DAYS}天")

    finite_mask = np.isfinite(day_matrix)
    if not bool(finite_mask.all()):
        reasons.append("存在非有限负荷值")
        daily_abnormal |= ~finite_mask.all(axis=1)

    mat = np.nan_to_num(day_matrix.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    if (mat < 0).any():
        reasons.append("存在负负荷值")
        daily_abnormal |= (mat < 0).any(axis=1)

    clipped_mat = np.clip(mat, 0.0, None)
    day_energy = clipped_mat.sum(axis=1)
    positive_energy = day_energy[day_energy > 1e-9]
    if positive_energy.size == 0:
        reasons.append("全周负荷接近零")
        daily_abnormal[:] = True
    else:
        median_energy = float(np.median(positive_energy))
        low_mask = day_energy < median_energy * WEEK_QUALITY_LOW_ENERGY_RATIO
        high_mask = day_energy > median_energy * WEEK_QUALITY_HIGH_ENERGY_RATIO
        if bool(low_mask.any()):
            reasons.append("存在疑似停电/缺测日")
            daily_abnormal |= low_mask
        if bool(high_mask.any()):
            reasons.append("存在疑似异常高能量日")
            daily_abnormal |= high_mask

    flat_positive = clipped_mat[clipped_mat > 1e-9]
    if flat_positive.size >= 24:
        p95 = float(np.percentile(flat_positive, 95))
        max_value = float(flat_positive.max())
        if p95 > 1e-9 and max_value / p95 >= WEEK_QUALITY_SPIKE_TO_P95_RATIO:
            reasons.append("存在疑似孤立尖峰")
            daily_abnormal |= (clipped_mat.max(axis=1) / max(p95, 1e-9)) >= WEEK_QUALITY_SPIKE_TO_P95_RATIO

    abnormal_count = int(daily_abnormal.sum())
    if abnormal_count >= max(2, int(np.ceil(max(n_days, 1) * 0.35))):
        reasons.append("异常日占比过高")

    ok = len(reasons) == 0
    return {
        "ok": bool(ok),
        "reason": "质量合格" if ok else "；".join(dict.fromkeys(reasons)),
        "abnormal_day_count": abnormal_count,
        "daily_abnormal": daily_abnormal,
    }


def classify_one_week(week_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    result = week_df[["日期", "星期序号", "星期", "周起始日"]].copy()
    day_matrix = week_df.loc[:, list(range(POINTS_PER_DAY))].to_numpy(dtype=float)
    n_days = len(week_df)
    quality = assess_week_data_quality(day_matrix)
    result["数据质量合格"] = quality["ok"]
    result["数据质量说明"] = quality["reason"]
    result["异常负荷日"] = quality["daily_abnormal"]
    labels = np.zeros(n_days, dtype=int)
    model_count = 1
    silhouette = np.nan
    profile_gap = np.nan
    energy_gap = np.nan
    if n_days >= 4:
        feature = _build_day_features(day_matrix)
        feature_std = StandardScaler().fit_transform(feature)
        km = KMeans(n_clusters=2, n_init=10, random_state=RANDOM_STATE)
        labels_2 = km.fit_predict(feature_std)
        counts = pd.Series(labels_2).value_counts()
        if counts.min() >= 2:
            silhouette = silhouette_score(feature_std, labels_2)
            center0 = day_matrix[labels_2 == 0].mean(axis=0)
            center1 = day_matrix[labels_2 == 1].mean(axis=0)
            mean_level = max(day_matrix.mean(), 1e-9)
            profile_gap = np.mean(np.abs(center0 - center1)) / mean_level
            energy_gap = abs(day_matrix[labels_2 == 0].mean() - day_matrix[labels_2 == 1].mean()) / mean_level
            if silhouette >= WEEK_CLUSTER_SIL_THRESHOLD and (
                profile_gap >= WEEK_PROFILE_GAP_THRESHOLD or energy_gap >= WEEK_ENERGY_GAP_THRESHOLD
            ):
                labels = labels_2.copy()
                model_count = 2
    result["原始簇"] = labels
    if model_count == 1:
        result["初判周内类别名称"] = "同类日"
        result["初判周内类别编码"] = FINAL_CAT_CODE_MAP["同类日"]
        same_curve = day_matrix.mean(axis=0)
        weekly_curve = pd.DataFrame([same_curve], columns=TIME_LABELS)
        weekly_curve.insert(0, "模型名称", ["同类日模型"])
        weekly_curve.insert(0, "类别名称", ["同类日"])
        weekly_curve.insert(0, "类别编码", [FINAL_CAT_CODE_MAP["同类日"]])
        weekly_curve.insert(0, "判定说明", ["全周无明显工休差异"])
        weekly_curve.insert(0, "周起始日", [week_df["周起始日"].iloc[0]])
        summary = {
            "周起始日": week_df["周起始日"].iloc[0],
            "本周天数": n_days,
            "周内模型数": 1,
            "判定结论": "全周无明显工休差异",
            "工作日数量": 0,
            "休息日数量": 0,
            "同类日数量": n_days,
            "轮廓系数": None if pd.isna(silhouette) else float(silhouette),
            "曲线差异指标": None if pd.isna(profile_gap) else float(profile_gap),
            "能量差异指标": None if pd.isna(energy_gap) else float(energy_gap),
            "数据质量合格": bool(quality["ok"]),
            "数据质量说明": str(quality["reason"]),
            "异常负荷日数量": int(quality["abnormal_day_count"]),
        }
        return result, weekly_curve, summary
    temp = result.copy()
    temp["日均负荷"] = day_matrix.mean(axis=1)
    weekend_ratio = temp.groupby("原始簇")["星期序号"].apply(lambda s: (s >= 5).mean()).to_dict()
    mean_energy = temp.groupby("原始簇")["日均负荷"].mean().to_dict()
    ratio0 = weekend_ratio.get(0, 0)
    ratio1 = weekend_ratio.get(1, 0)
    if ratio0 > ratio1:
        rest_raw = 0
    elif ratio1 > ratio0:
        rest_raw = 1
    else:
        rest_raw = min(mean_energy, key=mean_energy.get)
    result["初判周内类别名称"] = np.where(result["原始簇"] == rest_raw, "休息日", "工作日")
    result["初判周内类别编码"] = result["初判周内类别名称"].map(FINAL_CAT_CODE_MAP)
    work_curve = day_matrix[result["初判周内类别名称"].to_numpy() == "工作日"].mean(axis=0)
    rest_curve = day_matrix[result["初判周内类别名称"].to_numpy() == "休息日"].mean(axis=0)
    weekly_curve = pd.DataFrame([work_curve, rest_curve], columns=TIME_LABELS)
    weekly_curve.insert(0, "模型名称", ["工作日模型", "休息日模型"])
    weekly_curve.insert(0, "类别名称", ["工作日", "休息日"])
    weekly_curve.insert(0, "类别编码", [FINAL_CAT_CODE_MAP["工作日"], FINAL_CAT_CODE_MAP["休息日"]])
    weekly_curve.insert(0, "判定说明", ["存在明显工休差异", "存在明显工休差异"])
    weekly_curve.insert(0, "周起始日", [week_df["周起始日"].iloc[0], week_df["周起始日"].iloc[0]])
    summary = {
        "周起始日": week_df["周起始日"].iloc[0],
        "本周天数": n_days,
        "周内模型数": 2,
        "判定结论": "存在明显工休差异",
        "工作日数量": int((result["初判周内类别名称"] == "工作日").sum()),
        "休息日数量": int((result["初判周内类别名称"] == "休息日").sum()),
        "同类日数量": 0,
        "轮廓系数": None if pd.isna(silhouette) else float(silhouette),
        "曲线差异指标": None if pd.isna(profile_gap) else float(profile_gap),
        "能量差异指标": None if pd.isna(energy_gap) else float(energy_gap),
        "数据质量合格": bool(quality["ok"]),
        "数据质量说明": str(quality["reason"]),
        "异常负荷日数量": int(quality["abnormal_day_count"]),
    }
    return result, weekly_curve, summary


def analyze_weekly_work_rest(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    day_result_list = []
    curve_list = []
    summary_list = []
    for _, week_df in daily.groupby("周起始日", sort=True):
        day_result, curve_df, summary = classify_one_week(week_df)
        day_result_list.append(day_result)
        curve_list.append(curve_df)
        summary_list.append(summary)
    weekly_day_result = pd.concat(day_result_list, ignore_index=True)
    weekly_curve_result = pd.concat(curve_list, ignore_index=True)
    weekly_summary_result = pd.DataFrame(summary_list)
    return weekly_day_result, weekly_curve_result, weekly_summary_result


def encode_week_pattern(week_day_result: pd.DataFrame, label_col: str = "初判周内类别名称") -> str:
    full_week = pd.DataFrame({"星期序号": list(range(7))})
    temp = week_day_result[["星期序号", label_col]].copy()
    temp = full_week.merge(temp, on="星期序号", how="left")
    temp["编码"] = temp[label_col].map(PATTERN_CHAR_MAP).fillna("M")
    return "".join(temp["编码"].tolist())


def infer_company_main_workrest_pattern(
    weekly_day_result: pd.DataFrame,
    weekly_summary_result: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    rows = []
    for week_start, grp in weekly_day_result.groupby("周起始日", sort=True):
        pattern_code = encode_week_pattern(grp, label_col="初判周内类别名称")
        summary_row = weekly_summary_result.loc[weekly_summary_result["周起始日"] == week_start].iloc[0]
        rows.append({
            "周起始日": week_start,
            "初判周模式编码": pattern_code,
            "初判周模式说明": pattern_to_text(pattern_code),
            "是否完整周": ("M" not in pattern_code),
            "本周天数": summary_row["本周天数"],
            "周内模型数": summary_row["周内模型数"],
            "判定结论": summary_row["判定结论"],
            "轮廓系数": summary_row["轮廓系数"],
            "曲线差异指标": summary_row["曲线差异指标"],
            "能量差异指标": summary_row["能量差异指标"],
            "数据质量合格": summary_row.get("数据质量合格", True),
            "数据质量说明": summary_row.get("数据质量说明", "质量合格"),
            "异常负荷日数量": summary_row.get("异常负荷日数量", 0),
        })
    week_pattern_df = pd.DataFrame(rows)
    valid_df = week_pattern_df[week_pattern_df["是否完整周"]].copy()
    pattern_count = (
        valid_df["初判周模式编码"]
        .value_counts()
        .rename_axis("周模式编码")
        .reset_index(name="出现周数")
    )
    if not pattern_count.empty:
        total_valid_weeks = pattern_count["出现周数"].sum()
        pattern_count["占完整周比例"] = pattern_count["出现周数"] / total_valid_weeks
        pattern_count["模式说明"] = pattern_count["周模式编码"].apply(pattern_to_text)
        main_pattern = pattern_count.iloc[0]["周模式编码"]
    else:
        pattern_count["占完整周比例"] = []
        pattern_count["模式说明"] = []
        main_pattern = None
    week_pattern_df["公司主工休模式"] = main_pattern
    week_pattern_df["公司主工休模式说明"] = pattern_to_text(main_pattern) if main_pattern else "无法识别"
    if main_pattern is not None:
        week_pattern_df["与主模式偏离天数"] = week_pattern_df["初判周模式编码"].apply(
            lambda x: count_pattern_mismatch(x, main_pattern)
        )
    else:
        week_pattern_df["与主模式偏离天数"] = None
    return week_pattern_df, pattern_count, main_pattern


def revise_week_labels_by_main_pattern(
    weekly_day_result: pd.DataFrame,
    weekly_summary_result: pd.DataFrame,
    week_pattern_df: pd.DataFrame,
    main_pattern: str | None,
) -> pd.DataFrame:
    revised_rows = []

    def finish_week(grp: pd.DataFrame, week_type: str, rule: str, *, use_for_modeling: bool, exclude_reason: str = "") -> pd.DataFrame:
        grp = grp.copy()
        grp["最终周内类别编码"] = grp["最终周内类别名称"].map(FINAL_CAT_CODE_MAP)
        grp["周类型"] = week_type
        grp["修正规则"] = rule
        grp["参与典型曲线建模"] = bool(use_for_modeling)
        grp["建模剔除原因"] = "" if use_for_modeling else exclude_reason
        return grp

    for week_start, grp in weekly_day_result.groupby("周起始日", sort=True):
        grp = grp.copy()
        pattern_row = week_pattern_df.loc[week_pattern_df["周起始日"] == week_start].iloc[0]
        summary_row = weekly_summary_result.loc[weekly_summary_result["周起始日"] == week_start].iloc[0]
        this_pattern = pattern_row["初判周模式编码"]
        silhouette = summary_row["轮廓系数"]
        quality_ok = bool(summary_row.get("数据质量合格", True))
        quality_reason = str(summary_row.get("数据质量说明", "质量合格"))
        grp["初判周模式编码"] = this_pattern
        grp["公司主工休模式"] = main_pattern
        grp["公司主工休模式说明"] = pattern_to_text(main_pattern) if main_pattern else "无法识别"
        grp["与主模式偏离天数"] = count_pattern_mismatch(this_pattern, main_pattern) if main_pattern else None
        if main_pattern is None:
            grp["最终周内类别名称"] = grp["初判周内类别名称"]
            use_for_modeling = quality_ok
            rule = "未识别到公司主工休模式，保留初判结果"
            if not quality_ok:
                rule = f"{rule}；该周数据质量异常，不参与典型曲线均值"
            revised_rows.append(
                finish_week(
                    grp,
                    "无法识别主模式",
                    rule,
                    use_for_modeling=use_for_modeling,
                    exclude_reason=quality_reason,
                )
            )
            continue

        def apply_main_pattern(day_idx: int) -> str:
            ch = main_pattern[day_idx]
            return PATTERN_CHAR_TO_NAME.get(ch, "同类日")

        if not quality_ok:
            grp["最终周内类别名称"] = grp["星期序号"].apply(apply_main_pattern)
            revised_rows.append(
                finish_week(
                    grp,
                    "数据质量修正周",
                    f"数据质量异常（{quality_reason}），按公司主工休模式修正标签并剔除建模均值",
                    use_for_modeling=False,
                    exclude_reason=quality_reason,
                )
            )
            continue

        if this_pattern == main_pattern:
            grp["最终周内类别名称"] = grp["初判周内类别名称"]
            revised_rows.append(
                finish_week(grp, "主模式周", "与主模式完全一致", use_for_modeling=True)
            )
            continue
        if this_pattern == "SSSSSSS":
            grp["最终周内类别名称"] = grp["初判周内类别名称"]
            revised_rows.append(
                finish_week(grp, "特殊周", "本周为 SSSSSSS，特殊周保留", use_for_modeling=True)
            )
            continue
        if silhouette is not None and not pd.isna(silhouette) and silhouette >= SPECIAL_WEEK_SIL_THRESHOLD:
            grp["最终周内类别名称"] = grp["初判周内类别名称"]
            revised_rows.append(
                finish_week(
                    grp,
                    "特殊周",
                    f"与主模式不一致且轮廓系数≥{SPECIAL_WEEK_SIL_THRESHOLD:.2f}，特殊周保留",
                    use_for_modeling=True,
                )
            )
            continue
        grp["最终周内类别名称"] = grp["星期序号"].apply(apply_main_pattern)
        revised_rows.append(
            finish_week(
                grp,
                "主模式修正周",
                "轻微偏离主模式且分类不够稳定，按主模式修正",
                use_for_modeling=True,
            )
        )
    revised_day_result = pd.concat(revised_rows, ignore_index=True)
    return revised_day_result


def build_weekly_feature_table(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for week_start, x in daily.groupby("周起始日", sort=True):
        mat = x.loc[:, list(range(POINTS_PER_DAY))].to_numpy(dtype=float)
        day_mean = x.loc[:, list(range(POINTS_PER_DAY))].mean(axis=1)
        day_peak = x.loc[:, list(range(POINTS_PER_DAY))].max(axis=1)
        day_valley = x.loc[:, list(range(POINTS_PER_DAY))].min(axis=1)
        rows.append(
            {
                "周起始日": week_start,
                "周内天数": len(x),
                "周平均负荷": float(mat.mean()),
                "周峰值负荷": float(mat.max()),
                "周谷值负荷": float(mat.min()),
                "周负荷标准差": float(mat.std()),
                "周平均日峰谷差": float((day_peak - day_valley).mean()),
                "周日均负荷": float(day_mean.mean()),
            }
        )
    return pd.DataFrame(rows)


def classify_annual_periods(weekly_feature: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if weekly_feature.empty:
        raise ValueError("weekly_feature 为空，无法进行年度峰谷分段。")
    out = weekly_feature.copy().reset_index(drop=True)
    n_weeks = len(out)
    class_count = min(YEAR_LEVEL_COUNT, n_weeks)
    sorted_idx = out.sort_values(["周平均负荷", "周峰值负荷"], ascending=[False, False]).index.to_numpy()
    codes = np.ones(n_weeks, dtype=int)
    for pos, idx in enumerate(sorted_idx):
        codes[int(idx)] = min(int(pos * class_count / max(n_weeks, 1)) + 1, class_count)

    out["原始年类簇"] = codes
    out["年类编码"] = codes
    out["年类名称"] = out["年类编码"].apply(lambda code: YEAR_LEVEL_NAMES.get(int(code), f"负荷水平{int(code)}"))
    summary = (
        out.groupby(["年类编码", "年类名称"], as_index=False)
        .agg(
            周数=("周起始日", "count"),
            平均周负荷=("周平均负荷", "mean"),
            平均周峰值=("周峰值负荷", "mean"),
            平均周谷值=("周谷值负荷", "mean"),
        )
        .sort_values("年类编码")
    )
    summary.insert(0, "自动识别年类总数", class_count)
    summary.insert(1, "最佳轮廓系数", None)
    summary.insert(2, "年度分档方式", "按周平均负荷固定五档分位")
    return out, summary


def build_final_daily_mapping(
    daily: pd.DataFrame,
    revised_day_result: pd.DataFrame,
    annual_period_result: pd.DataFrame,
) -> pd.DataFrame:
    mapping = daily[["日期", "星期", "星期序号", "周起始日"]].copy()
    day_cols = [
        "日期",
        "初判周内类别名称",
        "初判周内类别编码",
        "最终周内类别名称",
        "最终周内类别编码",
        "初判周模式编码",
        "公司主工休模式",
        "公司主工休模式说明",
        "与主模式偏离天数",
        "周类型",
        "修正规则",
        "数据质量合格",
        "数据质量说明",
        "异常负荷日",
        "参与典型曲线建模",
        "建模剔除原因",
    ]
    mapping = mapping.merge(revised_day_result[day_cols], on="日期", how="left")
    mapping = mapping.merge(
        annual_period_result[["周起始日", "年类编码", "年类名称"]],
        on="周起始日",
        how="left",
    )
    mapping["组合模型编号"] = mapping.apply(
        lambda r: f"({int(r['最终周内类别编码'])},{int(r['年类编码'])})",
        axis=1
    )
    mapping["组合模型名称"] = mapping["最终周内类别名称"] + "-" + mapping["年类名称"]
    mapping = mapping.sort_values("日期").reset_index(drop=True)
    return mapping


def merge_sparse_combo_models(
    daily: pd.DataFrame,
    daily_mapping: pd.DataFrame,
    min_sample_days: int = MIN_COMBO_SAMPLE_DAYS,
) -> pd.DataFrame:
    mapping = daily_mapping.copy()
    if mapping.empty or "组合模型编号" not in mapping.columns:
        return mapping

    mapping["原始组合模型编号"] = mapping["组合模型编号"]
    mapping["原始组合模型名称"] = mapping["组合模型名称"]
    mapping["组合合并说明"] = "未合并"

    time_cols = list(range(POINTS_PER_DAY))
    merged = daily[["日期", *time_cols]].merge(mapping, on="日期", how="left")
    stats: dict[str, dict] = {}
    for model_id, grp in merged.groupby("组合模型编号", sort=True):
        if pd.isna(model_id):
            continue
        mat = grp[time_cols].to_numpy(dtype=float)
        stats[str(model_id)] = {
            "count": int(len(grp)),
            "curve": mat.mean(axis=0),
            "name": str(grp["组合模型名称"].iloc[0]),
            "day_code": int(grp["最终周内类别编码"].iloc[0]),
            "year_code": int(grp["年类编码"].iloc[0]),
        }

    if len(stats) <= 1:
        return mapping

    stable_ids = [model_id for model_id, meta in stats.items() if meta["count"] >= min_sample_days]
    if not stable_ids:
        return mapping

    replacements: dict[str, str] = {}
    for model_id, meta in stats.items():
        if meta["count"] >= min_sample_days:
            continue
        same_day_candidates = [
            candidate_id for candidate_id in stable_ids
            if stats[candidate_id]["day_code"] == meta["day_code"]
        ]
        candidates = same_day_candidates or stable_ids
        target_id = min(
            candidates,
            key=lambda candidate_id: (
                0 if stats[candidate_id]["day_code"] == meta["day_code"] else 1,
                abs(stats[candidate_id]["year_code"] - meta["year_code"]),
                float(np.linalg.norm(meta["curve"] - stats[candidate_id]["curve"])),
            ),
        )
        replacements[model_id] = target_id

    for source_id, target_id in replacements.items():
        mask = mapping["组合模型编号"].astype(str) == source_id
        target = stats[target_id]
        mapping.loc[mask, "组合模型编号"] = target_id
        mapping.loc[mask, "组合模型名称"] = target["name"]
        mapping.loc[mask, "组合合并说明"] = (
            f"样本天数{stats[source_id]['count']}<{min_sample_days}，"
            f"并入{target_id} {target['name']}"
        )

    return mapping.sort_values("日期").reset_index(drop=True)


def build_model_library(daily: pd.DataFrame, daily_mapping: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping_cols = [c for c in daily_mapping.columns if c != "日期"]
    merged = daily.merge(
        daily_mapping[["日期", *mapping_cols]],
        on="日期",
        how="left",
    )
    time_cols = list(range(POINTS_PER_DAY))
    curve_rows = []
    summary_rows = []
    total_days = max(len(daily_mapping), 1)
    for model_id, grp in merged.groupby("组合模型编号", sort=True):
        use_mask = grp.get("参与典型曲线建模", pd.Series(True, index=grp.index)).fillna(True).astype(bool)
        curve_source = grp[use_mask].copy()
        if curve_source.empty:
            curve_source = grp.copy()
        mat = curve_source[time_cols].to_numpy(dtype=float)
        mean_curve = mat.mean(axis=0)
        model_name = grp["组合模型名称"].iloc[0]
        mapped_days = int(len(grp))
        curve_days = int(len(curve_source))
        merged_sources = sorted(set(grp.get("原始组合模型编号", grp["组合模型编号"]).astype(str).tolist()))
        merged_day_count = int((grp.get("组合合并说明", pd.Series("未合并", index=grp.index)) != "未合并").sum())
        summary_rows.append(
            {
                "组合模型编号": model_id,
                "组合模型名称": model_name,
                "包含天数": mapped_days,
                "年度权重天数": mapped_days,
                "年度权重比例": round(mapped_days / total_days, 6),
                "曲线建模天数": curve_days,
                "曲线建模占比": round(curve_days / max(mapped_days, 1), 6),
                "合并来源组合数": len(merged_sources),
                "合并来源组合": ",".join(merged_sources),
                "被合并日期数": merged_day_count,
                "平均日负荷": float(mat.mean()),
                "平均日峰值": float(mat.max(axis=1).mean()),
                "平均日谷值": float(mat.min(axis=1).mean()),
            }
        )
        row = pd.DataFrame([mean_curve], columns=TIME_LABELS)
        row.insert(0, "曲线建模天数", curve_days)
        row.insert(0, "年度权重比例", round(mapped_days / total_days, 6))
        row.insert(0, "年度权重天数", mapped_days)
        row.insert(0, "组合模型名称", model_name)
        row.insert(0, "组合模型编号", model_id)
        curve_rows.append(row)
    curve_df = pd.concat(curve_rows, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows).sort_values("组合模型编号").reset_index(drop=True)
    return summary_df, curve_df


def plot_weekly_work_rest_final(daily_mapping: pd.DataFrame, out_file: Path) -> None:
    plot_df = daily_mapping.copy()
    plot_df["日期"] = pd.to_datetime(plot_df["日期"])
    y_map = {"工作日": 1, "休息日": 2, "同类日": 3}
    color_map = {"工作日": "#54A24B", "休息日": "#E45756", "同类日": "#4C78A8"}
    plot_df["y"] = plot_df["最终周内类别名称"].map(y_map).fillna(0)
    colors = plot_df["最终周内类别名称"].map(color_map).fillna("#999999")
    plt.figure(figsize=(15, 4.2))
    plt.scatter(plot_df["日期"], plot_df["y"], c=colors, s=22)
    plt.yticks([1, 2, 3], ["工作日", "休息日", "同类日"])
    plt.xlabel("日期")
    plt.ylabel("最终周内类别")
    plt.title("全年逐日工休划分结果（最终，1h级）")
    plt.grid(alpha=0.25, linestyle="--")
    plt.tight_layout()
    plt.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close()


def plot_annual_periods(annual_period_result: pd.DataFrame, out_file: Path) -> None:
    plot_df = annual_period_result.copy()
    plot_df["周起始日"] = pd.to_datetime(plot_df["周起始日"])
    plt.figure(figsize=(15, 4.5))
    for code, grp in plot_df.groupby("年类编码", sort=True):
        plt.scatter(
            grp["周起始日"],
            grp["周平均负荷"],
            label=f"年类{code}-{grp['年类名称'].iloc[0]}",
            s=35
        )
    plt.plot(plot_df["周起始日"], plot_df["周平均负荷"], alpha=0.35)
    plt.xlabel("周起始日")
    plt.ylabel("周平均负荷")
    plt.title("年度周尺度峰谷分段结果（1h级）")
    plt.grid(alpha=0.25, linestyle="--")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close()


def plot_model_library(model_curve_df: pd.DataFrame, out_file: Path) -> None:
    time_cols = [c for c in TIME_LABELS if c in model_curve_df.columns]
    if len(time_cols) != POINTS_PER_DAY:
        raise ValueError(f"组合典型日曲线缺少标准 24 小时时刻列，当前识别到 {len(time_cols)} 个。")
    x = np.arange(len(time_cols))
    plt.figure(figsize=(15, 6))
    for _, row in model_curve_df.iterrows():
        plt.plot(x, row[time_cols].to_numpy(dtype=float), label=f"{row['组合模型编号']} {row['组合模型名称']}")
    plt.xticks(np.arange(len(time_cols)), time_cols, rotation=45)
    plt.xlabel("时刻")
    plt.ylabel("负荷")
    plt.title("组合典型日负荷模型曲线（1h级）")
    plt.grid(alpha=0.25, linestyle="--")
    plt.legend(fontsize=8, ncol=2)
    plt.tight_layout()
    plt.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close()


def save_excel_results(
    company_dir: Path,
    weekly_day_result: pd.DataFrame,
    revised_day_result: pd.DataFrame,
    weekly_curve_result: pd.DataFrame,
    weekly_summary_result: pd.DataFrame,
    week_pattern_df: pd.DataFrame,
    pattern_count_df: pd.DataFrame,
    annual_period_result: pd.DataFrame,
    annual_summary_result: pd.DataFrame,
    daily_mapping: pd.DataFrame,
    model_summary_df: pd.DataFrame,
    model_curve_df: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(company_dir / "00_公司主工休模式识别结果.xlsx", engine="openpyxl") as writer:
        week_pattern_df.to_excel(writer, sheet_name="每周模式识别", index=False)
        pattern_count_df.to_excel(writer, sheet_name="模式频次统计", index=False)
    with pd.ExcelWriter(company_dir / "01_每周工休划分结果.xlsx", engine="openpyxl") as writer:
        weekly_day_result.to_excel(writer, sheet_name="逐日初判结果", index=False)
        revised_day_result.to_excel(writer, sheet_name="逐日修正结果", index=False)
        weekly_summary_result.to_excel(writer, sheet_name="每周摘要", index=False)
        weekly_curve_result.to_excel(writer, sheet_name="每周典型曲线", index=False)
    with pd.ExcelWriter(company_dir / "02_年度峰谷分段结果.xlsx", engine="openpyxl") as writer:
        annual_period_result.to_excel(writer, sheet_name="每周分段结果", index=False)
        annual_summary_result.to_excel(writer, sheet_name="年类摘要", index=False)
    daily_mapping.to_excel(company_dir / "03_全年逐日模型映射表.xlsx", index=False)
    with pd.ExcelWriter(company_dir / "04_组合典型日负荷模型库.xlsx", engine="openpyxl") as writer:
        model_summary_df.to_excel(writer, sheet_name="模型摘要", index=False)
        model_curve_df.to_excel(writer, sheet_name="模型24点曲线", index=False)


def save_summary_txt(
    company_dir: Path,
    company_name: str,
    week_pattern_df: pd.DataFrame,
    pattern_count_df: pd.DataFrame,
    daily_mapping: pd.DataFrame,
    annual_summary_result: pd.DataFrame,
    model_summary_df: pd.DataFrame,
) -> None:
    main_pattern = None
    main_pattern_text = "无法识别"
    if not week_pattern_df.empty:
        main_pattern = week_pattern_df["公司主工休模式"].dropna().iloc[0] if week_pattern_df["公司主工休模式"].notna().any() else None
        main_pattern_text = pattern_to_text(main_pattern) if main_pattern else "无法识别"
    lines = []
    lines.append(f"公司文件名：{company_name}.xlsx")
    lines.append(f"全年有效天数：{len(daily_mapping)}")
    lines.append(f"公司主工休模式：{main_pattern if main_pattern else '无法识别'}")
    lines.append(f"公司主工休模式说明：{main_pattern_text}")
    lines.append("")
    if not pattern_count_df.empty:
        lines.append("完整周模式频次统计：")
        for _, row in pattern_count_df.iterrows():
            lines.append(
                f"  {row['周模式编码']} | 出现周数={row['出现周数']} | 占完整周比例={row['占完整周比例']:.2%} | {row['模式说明']}"
            )
        lines.append("")
    if not annual_summary_result.empty:
        lines.append(f"自动识别年度分段数：{annual_summary_result['自动识别年类总数'].iloc[0]}")
        lines.append(f"最终组合模型个数：{len(model_summary_df)}")
        lines.append("")
    if not daily_mapping.empty:
        week_type_stat = daily_mapping[["周起始日", "周类型"]].drop_duplicates()["周类型"].value_counts().to_dict()
        lines.append(f"周类型统计：{week_type_stat}")
        modeling_mask = daily_mapping.get("参与典型曲线建模", pd.Series(True, index=daily_mapping.index)).astype(bool)
        excluded_days = int((~modeling_mask).sum())
        merged_days = int((daily_mapping.get("组合合并说明", pd.Series("未合并", index=daily_mapping.index)) != "未合并").sum())
        lines.append(f"未参与典型曲线均值的低质量天数：{excluded_days}")
        lines.append(f"小样本组合合并影响天数：{merged_days}")
        lines.append("")
    lines.append("最终组合模型：")
    for _, row in model_summary_df.iterrows():
        lines.append(
            f"  {row['组合模型编号']} | {row['组合模型名称']} | 包含天数={row['包含天数']} | 平均日负荷={row['平均日负荷']:.2f}"
        )
    (company_dir / "05_结果说明.txt").write_text("\n".join(lines), encoding="utf-8")


def process_one_company(file_path: Path, output_root: Path) -> None:
    company_name = file_path.stem
    company_dir = output_root / company_name
    company_dir.mkdir(parents=True, exist_ok=True)
    df_1h = read_load_excel(file_path)
    daily, _ = build_daily_profiles(df_1h)
    if daily.empty:
        raise ValueError(f"{file_path.name} 无法构成完整的 1h 日负荷曲线。")
    weekly_day_result, weekly_curve_result, weekly_summary_result = analyze_weekly_work_rest(daily)
    week_pattern_df, pattern_count_df, main_pattern = infer_company_main_workrest_pattern(
        weekly_day_result,
        weekly_summary_result
    )
    revised_day_result = revise_week_labels_by_main_pattern(
        weekly_day_result,
        weekly_summary_result,
        week_pattern_df,
        main_pattern
    )
    annual_feature = build_weekly_feature_table(daily)
    annual_period_result, annual_summary_result = classify_annual_periods(annual_feature)
    daily_mapping = build_final_daily_mapping(
        daily,
        revised_day_result,
        annual_period_result
    )
    daily_mapping = merge_sparse_combo_models(daily, daily_mapping)
    model_summary_df, model_curve_df = build_model_library(daily, daily_mapping)
    save_excel_results(
        company_dir,
        weekly_day_result,
        revised_day_result,
        weekly_curve_result,
        weekly_summary_result,
        week_pattern_df,
        pattern_count_df,
        annual_period_result,
        annual_summary_result,
        daily_mapping,
        model_summary_df,
        model_curve_df,
    )
    plot_weekly_work_rest_final(daily_mapping, company_dir / "01_全年工休划分示意图.svg")
    plot_annual_periods(annual_period_result, company_dir / "02_年度峰谷分段示意图.svg")
    plot_model_library(model_curve_df, company_dir / "03_组合典型日曲线.svg")
    save_summary_txt(
        company_dir,
        company_name,
        week_pattern_df,
        pattern_count_df,
        daily_mapping,
        annual_summary_result,
        model_summary_df,
    )


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    output_root = base_dir / OUTPUT_ROOT_NAME
    output_root.mkdir(exist_ok=True)
    excel_files = [p for p in base_dir.glob("*.xlsx") if not p.name.startswith("~$")]
    if not excel_files:
        print("当前脚本同级目录下未找到任何 xlsx 文件。")
        return
    for file_path in excel_files:
        try:
            print(f"开始处理：{file_path.name}")
            process_one_company(file_path, output_root)
            print(f"处理完成：{file_path.name}")
        except Exception as exc:
            print(f"处理失败：{file_path.name} -> {exc}")
    print("全部处理结束。")
    print(f"结果目录：{output_root}")


if __name__ == "__main__":
    main()


def process_raw_data(raw_excel_path: str | Path, output_dir: str | Path) -> dict:
    file_path = Path(raw_excel_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    process_one_company(file_path, output_root)

    # Flatten: move files from the subdirectory created by process_one_company up to output_root
    nested_dir = output_root / file_path.stem
    if nested_dir.is_dir():
        for f in nested_dir.iterdir():
            shutil.move(str(f), str(output_root / f.name))
        nested_dir.rmdir()

    charts = sorted([p.name for p in output_root.glob("*.svg")], key=lambda x: x)
    excel_files = sorted([p.name for p in output_root.glob("*.xlsx")], key=lambda x: x)
    return {"charts": charts, "excel_files": excel_files, "error": None}
