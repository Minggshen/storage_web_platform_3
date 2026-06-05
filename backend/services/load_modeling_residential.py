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

# =========================================================
# 参数区
# =========================================================
OUTPUT_ROOT_NAME = "居民典型日负荷1h级模型"

TARGET_FREQ = "1h"

MIN_CLUSTERS = 2
MAX_CLUSTERS = 8
DAILY_CLUSTER_SIL_THRESHOLD = 0.08
RANDOM_STATE = 42

MANUAL_HOLIDAYS = []

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def get_points_per_day(freq: str) -> int:
    td = pd.to_timedelta(freq)
    return int(pd.Timedelta(days=1) / td)


def get_time_labels(freq: str) -> list[str]:
    points = get_points_per_day(freq)
    step_minutes = int(pd.to_timedelta(freq).total_seconds() // 60)
    labels = []
    for i in range(points):
        total_minutes = i * step_minutes
        hh = total_minutes // 60
        mm = total_minutes % 60
        labels.append(f"{hh:02d}:{mm:02d}")
    return labels


POINTS_PER_DAY = get_points_per_day(TARGET_FREQ)
TIME_LABELS = get_time_labels(TARGET_FREQ)


def to_holiday_set(manual_holidays: list[str]) -> set:
    result = set()
    for x in manual_holidays:
        try:
            result.add(pd.to_datetime(x).date())
        except Exception:
            pass
    return result


HOLIDAY_SET = to_holiday_set(MANUAL_HOLIDAYS)


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
    raw = raw.dropna(subset=["时间", "负荷"]).sort_values("时间")
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
    df_target = df.resample(TARGET_FREQ).mean()
    df_target["负荷"] = df_target["负荷"].interpolate(method="time", limit_direction="both")
    df_target["负荷"] = df_target["负荷"].ffill().bfill()
    return df_target.reset_index()


def build_daily_profiles(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["日期"] = df["时间"].dt.date
    df["月份"] = df["时间"].dt.month
    df["星期序号"] = df["时间"].dt.weekday
    df["星期"] = df["星期序号"].map({
        0: "周一", 1: "周二", 2: "周三", 3: "周四",
        4: "周五", 5: "周六", 6: "周日"
    })
    df["是否周末"] = (df["星期序号"] >= 5).astype(int)
    df["是否节假日"] = df["日期"].apply(lambda x: 1 if x in HOLIDAY_SET else 0)
    step_minutes = int(pd.to_timedelta(TARGET_FREQ).total_seconds() // 60)
    df["时段序号"] = ((df["时间"].dt.hour * 60 + df["时间"].dt.minute) // step_minutes).astype(int)
    pivot = df.pivot_table(index="日期", columns="时段序号", values="负荷", aggfunc="mean")
    pivot = pivot.reindex(columns=range(POINTS_PER_DAY))
    pivot = pivot.dropna(how="any")
    daily = pivot.reset_index()
    meta = df.groupby("日期").agg(
        月份=("月份", "first"),
        星期序号=("星期序号", "first"),
        星期=("星期", "first"),
        是否周末=("是否周末", "first"),
        是否节假日=("是否节假日", "first"),
    ).reset_index()
    daily = daily.merge(meta, on="日期", how="left")
    daily = daily.sort_values("日期").reset_index(drop=True)
    return daily


def build_time_masks(points_per_day: int) -> dict[str, np.ndarray]:
    slot_hours = np.arange(points_per_day) * (24 / points_per_day)
    masks = {
        "夜间": (slot_hours >= 0) & (slot_hours < 6),
        "早高峰": (slot_hours >= 6) & (slot_hours < 10),
        "白天": (slot_hours >= 10) & (slot_hours < 17),
        "晚高峰": (slot_hours >= 17) & (slot_hours < 22),
        "深夜": (slot_hours >= 22) & (slot_hours < 24),
    }
    return masks


TIME_MASKS = build_time_masks(POINTS_PER_DAY)


def safe_zone_mean(mat: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if mask.sum() == 0:
        return np.zeros(mat.shape[0])
    return mat[:, mask].mean(axis=1)


def season_group(month: int) -> str:
    if month in [12, 1, 2]:
        return "冬季"
    elif month in [6, 7, 8, 9]:
        return "夏季"
    else:
        return "过渡季"


def build_daily_feature_matrix(daily: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    time_cols = list(range(POINTS_PER_DAY))
    mat = daily[time_cols].to_numpy(dtype=float)
    day_mean = mat.mean(axis=1)
    day_peak = mat.max(axis=1)
    day_valley = mat.min(axis=1)
    day_std = mat.std(axis=1)
    peak_valley_diff = day_peak - day_valley
    load_factor = np.divide(day_mean, day_peak, out=np.zeros_like(day_mean), where=day_peak != 0)
    morning_mean = safe_zone_mean(mat, TIME_MASKS["早高峰"])
    daytime_mean = safe_zone_mean(mat, TIME_MASKS["白天"])
    evening_mean = safe_zone_mean(mat, TIME_MASKS["晚高峰"])
    night_mean = safe_zone_mean(mat, TIME_MASKS["夜间"])
    late_mean = safe_zone_mean(mat, TIME_MASKS["深夜"])
    morning_ratio = np.divide(morning_mean, day_mean, out=np.zeros_like(day_mean), where=day_mean != 0)
    daytime_ratio = np.divide(daytime_mean, day_mean, out=np.zeros_like(day_mean), where=day_mean != 0)
    evening_ratio = np.divide(evening_mean, day_mean, out=np.zeros_like(day_mean), where=day_mean != 0)
    night_ratio = np.divide(night_mean, day_mean, out=np.zeros_like(day_mean), where=day_mean != 0)
    late_ratio = np.divide(late_mean, day_mean, out=np.zeros_like(day_mean), where=day_mean != 0)
    shape_feature = np.divide(
        mat,
        day_mean[:, None],
        out=np.zeros_like(mat),
        where=day_mean[:, None] != 0
    )
    month = daily["月份"].to_numpy(dtype=float)
    month_sin = np.sin(2 * np.pi * month / 12)
    month_cos = np.cos(2 * np.pi * month / 12)
    is_weekend = daily["是否周末"].to_numpy(dtype=float)
    is_holiday = daily["是否节假日"].to_numpy(dtype=float)
    feature = np.concatenate(
        [
            shape_feature,
            day_mean[:, None],
            day_peak[:, None],
            day_valley[:, None],
            day_std[:, None],
            peak_valley_diff[:, None],
            load_factor[:, None],
            morning_ratio[:, None],
            daytime_ratio[:, None],
            evening_ratio[:, None],
            night_ratio[:, None],
            late_ratio[:, None],
            is_weekend[:, None],
            is_holiday[:, None],
            month_sin[:, None],
            month_cos[:, None],
        ],
        axis=1,
    )
    aux = pd.DataFrame({
        "日期": daily["日期"],
        "日均负荷": day_mean,
        "日峰值": day_peak,
        "日谷值": day_valley,
        "日标准差": day_std,
        "峰谷差": peak_valley_diff,
        "负荷率": load_factor,
        "早高峰占比": morning_ratio,
        "白天占比": daytime_ratio,
        "晚高峰占比": evening_ratio,
        "夜间占比": night_ratio,
        "深夜占比": late_ratio,
    })
    return feature, aux


def cluster_daily_models(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature, aux = build_daily_feature_matrix(daily)
    n_days = len(daily)
    result = daily.copy().merge(aux, on="日期", how="left")
    if n_days < 10:
        result["模型编号"] = "R01"
        result["原始簇"] = 0
        eval_df = pd.DataFrame([{
            "聚类数k": 1,
            "轮廓系数": None,
            "是否采用": True,
            "说明": "有效天数过少，直接视为 1 类"
        }])
        return result, eval_df
    X_std = StandardScaler().fit_transform(feature)
    eval_rows = []
    best_score = -1.0
    best_k = 1
    best_labels = np.zeros(n_days, dtype=int)
    max_k = min(MAX_CLUSTERS, n_days - 1)
    min_k = min(MIN_CLUSTERS, max_k)
    for k in range(min_k, max_k + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(X_std)
        counts = pd.Series(labels).value_counts()
        if counts.min() < 2:
            eval_rows.append({
                "聚类数k": k,
                "轮廓系数": None,
                "是否采用": False,
                "说明": "存在样本数小于2的簇，跳过"
            })
            continue
        score = silhouette_score(X_std, labels)
        eval_rows.append({
            "聚类数k": k,
            "轮廓系数": round(score, 4),
            "是否采用": False,
            "说明": ""
        })
        if score > best_score:
            best_score = score
            best_k = k
            best_labels = labels.copy()
    if best_score < DAILY_CLUSTER_SIL_THRESHOLD:
        best_k = 1
        best_labels = np.zeros(n_days, dtype=int)
    eval_df = pd.DataFrame(eval_rows)
    if best_k == 1:
        eval_df = pd.concat([
            eval_df,
            pd.DataFrame([{
                "聚类数k": 1,
                "轮廓系数": None,
                "是否采用": True,
                "说明": f"最佳轮廓系数低于阈值 {DAILY_CLUSTER_SIL_THRESHOLD:.2f}，回退为 1 类"
            }])
        ], ignore_index=True)
    else:
        eval_df.loc[eval_df["聚类数k"] == best_k, "是否采用"] = True
        eval_df.loc[eval_df["聚类数k"] == best_k, "说明"] = "采用该聚类数"
    result["原始簇"] = best_labels
    cluster_order = (
        result.groupby("原始簇")["日期"]
        .count()
        .sort_values(ascending=False)
        .index
        .tolist()
    )
    raw_to_model = {raw: f"R{idx + 1:02d}" for idx, raw in enumerate(cluster_order)}
    result["模型编号"] = result["原始簇"].map(raw_to_model)
    return result, eval_df


def infer_shape_name(mean_curve: np.ndarray) -> str:
    daily_mean = mean_curve.mean()
    daily_std = mean_curve.std()
    def zone_avg(mask_name: str) -> float:
        mask = TIME_MASKS[mask_name]
        if mask.sum() == 0:
            return 0.0
        return float(mean_curve[mask].mean())
    morning = zone_avg("早高峰")
    daytime = zone_avg("白天")
    evening = zone_avg("晚高峰")
    night = zone_avg("夜间")
    late = zone_avg("深夜")
    if daily_mean == 0:
        return "平稳型"
    if daily_std / daily_mean < 0.10:
        return "平稳型"
    if (
        morning >= daily_mean * 1.05
        and evening >= daily_mean * 1.08
        and abs(morning - evening) / max(daily_mean, 1e-9) < 0.12
    ):
        return "早晚双峰型"
    if evening == max(morning, daytime, evening, night, late):
        if evening >= daily_mean * 1.10:
            return "晚高峰型"
    if daytime == max(morning, daytime, evening, night, late):
        if daytime >= daily_mean * 1.08:
            return "白天高平台型"
    if max(night, late) >= max(morning, daytime, evening):
        return "夜间偏高型"
    return "综合波动型"


def infer_season_name(month_series: pd.Series) -> str:
    season_count = month_series.map(season_group).value_counts()
    if season_count.empty:
        return "全年"
    top_season = season_count.idxmax()
    top_ratio = season_count.iloc[0] / season_count.sum()
    if top_ratio >= 0.60:
        return top_season
    return "全年"


def infer_daytype_name(weekend_share: float, holiday_share: float) -> str:
    if holiday_share >= 0.40:
        return "节假日型"
    if weekend_share >= 0.65:
        return "周末型"
    if weekend_share <= 0.35:
        return "工作日型"
    return "混合日型"


def build_model_library(clustered_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    time_cols = list(range(POINTS_PER_DAY))
    curve_rows = []
    summary_rows = []
    for model_id, grp in clustered_daily.groupby("模型编号", sort=True):
        mat = grp[time_cols].to_numpy(dtype=float)
        mean_curve = mat.mean(axis=0)
        season_name = infer_season_name(grp["月份"])
        daytype_name = infer_daytype_name(grp["是否周末"].mean(), grp["是否节假日"].mean())
        shape_name = infer_shape_name(mean_curve)
        model_name = f"{season_name}{daytype_name}{shape_name}"
        summary_rows.append({
            "模型编号": model_id,
            "模型名称": model_name,
            "包含天数": len(grp),
            "平均日负荷": float(mat.mean()),
            "平均日峰值": float(mat.max(axis=1).mean()),
            "平均日谷值": float(mat.min(axis=1).mean()),
            "平均峰谷差": float((mat.max(axis=1) - mat.min(axis=1)).mean()),
            "周末占比": float(grp["是否周末"].mean()),
            "节假日占比": float(grp["是否节假日"].mean()),
            "主要月份": ",".join(map(str, sorted(grp["月份"].value_counts().head(4).index.tolist()))),
            "季节属性": season_name,
            "日期属性": daytype_name,
            "曲线属性": shape_name,
        })
        row = pd.DataFrame([mean_curve], columns=TIME_LABELS)
        row.insert(0, "模型名称", model_name)
        row.insert(0, "模型编号", model_id)
        curve_rows.append(row)
    summary_df = pd.DataFrame(summary_rows).sort_values("模型编号").reset_index(drop=True)
    curve_df = pd.concat(curve_rows, ignore_index=True)
    return summary_df, curve_df


def build_daily_mapping(clustered_daily: pd.DataFrame, model_summary_df: pd.DataFrame) -> pd.DataFrame:
    mapping = clustered_daily[[
        "日期", "月份", "星期", "星期序号", "是否周末", "是否节假日",
        "模型编号", "日均负荷", "日峰值", "日谷值", "峰谷差", "负荷率",
        "早高峰占比", "白天占比", "晚高峰占比", "夜间占比", "深夜占比"
    ]].copy()
    mapping = mapping.merge(
        model_summary_df[["模型编号", "模型名称", "季节属性", "日期属性", "曲线属性"]],
        on="模型编号",
        how="left"
    )
    mapping = mapping.sort_values("日期").reset_index(drop=True)
    return mapping


def build_distribution_tables(daily_mapping: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    month_dist = (
        daily_mapping.pivot_table(
            index="月份",
            columns="模型编号",
            values="日期",
            aggfunc="count",
            fill_value=0
        )
        .reset_index()
    )
    weekday_dist = (
        daily_mapping.pivot_table(
            index="星期",
            columns="模型编号",
            values="日期",
            aggfunc="count",
            fill_value=0
        )
        .reindex(["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
        .reset_index()
    )
    return month_dist, weekday_dist


def plot_model_curves(model_curve_df: pd.DataFrame, out_file: Path) -> None:
    time_cols = [c for c in TIME_LABELS if c in model_curve_df.columns]
    if len(time_cols) != POINTS_PER_DAY:
        raise ValueError(f"居民典型日曲线缺少标准时刻列，当前识别到 {len(time_cols)} 个。")
    x = np.arange(len(time_cols))
    plt.figure(figsize=(15, 6))
    for _, row in model_curve_df.iterrows():
        plt.plot(x, row[time_cols].to_numpy(dtype=float), label=f"{row['模型编号']} {row['模型名称']}")
    tick_step = max(1, len(time_cols) // 12)
    tick_positions = np.arange(0, len(time_cols), tick_step)
    tick_labels = [time_cols[i] for i in tick_positions]
    plt.xticks(tick_positions, tick_labels, rotation=45)
    plt.xlabel("时刻")
    plt.ylabel("负荷")
    plt.title(f"居民典型日负荷模型曲线（{TARGET_FREQ}级）")
    plt.grid(alpha=0.25, linestyle="--")
    plt.legend(fontsize=8, ncol=2)
    plt.tight_layout()
    plt.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close()


def plot_daily_model_mapping(daily_mapping: pd.DataFrame, out_file: Path) -> None:
    plot_df = daily_mapping.copy()
    plot_df["日期"] = pd.to_datetime(plot_df["日期"])
    model_order = sorted(plot_df["模型编号"].dropna().unique().tolist())
    y_map = {m: i + 1 for i, m in enumerate(model_order)}
    plot_df["y"] = plot_df["模型编号"].map(y_map)
    plt.figure(figsize=(15, 4.5))
    plt.scatter(plot_df["日期"], plot_df["y"], s=18)
    plt.yticks(list(y_map.values()), list(y_map.keys()))
    plt.xlabel("日期")
    plt.ylabel("模型编号")
    plt.title("全年逐日居民模型映射结果")
    plt.grid(alpha=0.25, linestyle="--")
    plt.tight_layout()
    plt.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close()


def plot_month_distribution(month_dist: pd.DataFrame, out_file: Path) -> None:
    plot_df = month_dist.copy()
    x = plot_df["月份"].to_numpy()
    model_cols = [c for c in plot_df.columns if c != "月份"]
    plt.figure(figsize=(12, 5))
    bottom = np.zeros(len(plot_df))
    for col in model_cols:
        y = plot_df[col].to_numpy(dtype=float)
        plt.bar(x, y, bottom=bottom, label=col)
        bottom += y
    plt.xlabel("月份")
    plt.ylabel("天数")
    plt.title("各居民模型月度分布")
    plt.xticks(range(1, 13))
    plt.grid(axis="y", alpha=0.25, linestyle="--")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_file, format="svg", bbox_inches="tight")
    plt.close()


def save_excel_results(
    company_dir: Path,
    daily_mapping: pd.DataFrame,
    model_summary_df: pd.DataFrame,
    model_curve_df: pd.DataFrame,
    month_dist: pd.DataFrame,
    weekday_dist: pd.DataFrame,
    eval_df: pd.DataFrame,
) -> None:
    with pd.ExcelWriter(company_dir / "01_全年逐日模型映射表.xlsx", engine="openpyxl") as writer:
        daily_mapping.to_excel(writer, sheet_name="逐日映射", index=False)
        month_dist.to_excel(writer, sheet_name="月度分布", index=False)
        weekday_dist.to_excel(writer, sheet_name="星期分布", index=False)
    with pd.ExcelWriter(company_dir / "02_居民典型日模型库.xlsx", engine="openpyxl") as writer:
        model_summary_df.to_excel(writer, sheet_name="模型摘要", index=False)
        model_curve_df.to_excel(writer, sheet_name="模型曲线", index=False)
    with pd.ExcelWriter(company_dir / "03_聚类评估结果.xlsx", engine="openpyxl") as writer:
        eval_df.to_excel(writer, sheet_name="聚类数评估", index=False)


def save_summary_txt(
    company_dir: Path,
    company_name: str,
    daily_mapping: pd.DataFrame,
    model_summary_df: pd.DataFrame,
    eval_df: pd.DataFrame,
) -> None:
    lines = []
    lines.append(f"文件名称：{company_name}.xlsx")
    lines.append(f"目标建模粒度：{TARGET_FREQ}")
    lines.append(f"全年有效天数：{len(daily_mapping)}")
    lines.append(f"居民典型日模型数：{len(model_summary_df)}")
    lines.append(f"手动节假日数量：{len(HOLIDAY_SET)}")
    lines.append("")
    adopted = eval_df[eval_df["是否采用"]]
    if not adopted.empty:
        row = adopted.iloc[0]
        lines.append(f"采用聚类数：{row['聚类数k']}")
        lines.append(f"对应说明：{row['说明']}")
        if pd.notna(row["轮廓系数"]):
            lines.append(f"轮廓系数：{row['轮廓系数']}")
        lines.append("")
    lines.append("各模型摘要：")
    for _, r in model_summary_df.iterrows():
        lines.append(
            f"  {r['模型编号']} | {r['模型名称']} | "
            f"天数={r['包含天数']} | 平均日负荷={r['平均日负荷']:.2f} | "
            f"周末占比={r['周末占比']:.2%} | 节假日占比={r['节假日占比']:.2%}"
        )
    lines.append("")
    lines.append("节假日配置说明：")
    if len(HOLIDAY_SET) == 0:
        lines.append("  当前未配置手动节假日，代码仅识别是否周末。")
        lines.append("  若需提高居民建模效果，建议在 MANUAL_HOLIDAYS 中填写对应年份节假日。")
    else:
        lines.append("  已启用手动节假日识别。")
    (company_dir / "04_结果说明.txt").write_text("\n".join(lines), encoding="utf-8")


def process_one_company(file_path: Path, output_root: Path) -> None:
    company_name = file_path.stem
    company_dir = output_root / company_name
    company_dir.mkdir(parents=True, exist_ok=True)
    df = read_load_excel(file_path)
    daily = build_daily_profiles(df)
    if daily.empty:
        raise ValueError(f"{file_path.name} 无法构成完整的日负荷曲线。")
    clustered_daily, eval_df = cluster_daily_models(daily)
    model_summary_df, model_curve_df = build_model_library(clustered_daily)
    daily_mapping = build_daily_mapping(clustered_daily, model_summary_df)
    month_dist, weekday_dist = build_distribution_tables(daily_mapping)
    save_excel_results(
        company_dir,
        daily_mapping,
        model_summary_df,
        model_curve_df,
        month_dist,
        weekday_dist,
        eval_df,
    )
    plot_model_curves(model_curve_df, company_dir / "01_居民典型日曲线.svg")
    plot_daily_model_mapping(daily_mapping, company_dir / "02_全年逐日模型映射.svg")
    plot_month_distribution(month_dist, company_dir / "03_模型月度分布.svg")
    save_summary_txt(
        company_dir,
        company_name,
        daily_mapping,
        model_summary_df,
        eval_df,
    )


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    output_root = base_dir / OUTPUT_ROOT_NAME
    output_root.mkdir(exist_ok=True)
    excel_files = [
        p for p in base_dir.glob("*.xlsx")
        if not p.name.startswith("~$")
    ]
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

    # process_one_company creates output_root / file_path.stem / subdirectory.
    # Move all files up to output_root / to eliminate the extra nesting.
    nested_dir = output_root / file_path.stem
    if nested_dir.is_dir():
        for f in nested_dir.iterdir():
            shutil.move(str(f), str(output_root / f.name))
        nested_dir.rmdir()

    charts = sorted(
        [p.name for p in output_root.glob("*.svg")],
        key=lambda x: x
    )
    excel_files = sorted(
        [p.name for p in output_root.glob("*.xlsx")],
        key=lambda x: x
    )
    return {"charts": charts, "excel_files": excel_files, "error": None}
