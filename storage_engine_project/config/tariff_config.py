from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class TariffExcelSchema:
    """
    分时电价 Excel 字段约定。

    严格口径：
    1. 全网共用且仅允许 1 份逐日逐时电价表；
    2. 必须包含“日期”列；
    3. 必须包含 24 个小时电价列：电价_00 ~ 电价_23；
    4. 不允许旧格式；
    5. 不允许默认电价 fallback。
    """

    date_col: str = "日期"
    hourly_price_prefix: str = "电价_"
    hour_col_start: int = 0
    hour_col_end: int = 23

    @property
    def hourly_price_columns(self) -> Tuple[str, ...]:
        return tuple(
            f"{self.hourly_price_prefix}{hour:02d}"
            for hour in range(self.hour_col_start, self.hour_col_end + 1)
        )


@dataclass(frozen=True)
class TariffConfig:
    """
    电价配置。

    严格口径：
    1. 只能从唯一指定的 Excel 电价表读取；
    2. 不存在候选文件优先级；
    3. 不允许默认电价兜底；
    4. 读不到文件或字段不完整时直接报错。
    """

    excel_path: str
    days_per_year: int = 365
    hours_per_day: int = 24
    schema: TariffExcelSchema = field(default_factory=TariffExcelSchema)

    def __post_init__(self) -> None:
        if not str(self.excel_path).strip():
            raise ValueError("excel_path 不能为空。当前工程必须显式指定唯一电价 Excel 文件。")

        if self.days_per_year <= 0:
            raise ValueError("days_per_year 必须为正整数。")

        if self.hours_per_day != 24:
            raise ValueError("当前工程仅支持 24 点小时级电价，hours_per_day 必须为 24。")

        expected_cols = self.schema.hourly_price_columns
        if len(expected_cols) != self.hours_per_day:
            raise ValueError("schema.hourly_price_columns 数量必须等于 hours_per_day。")

    def resolve_excel_path(self, project_root: Path | None = None) -> Path:
        """
        解析唯一电价文件路径。
        """
        p = Path(self.excel_path)
        if p.is_absolute():
            return p.resolve()

        root = project_root or Path.cwd()
        return (root / p).resolve()

    def to_flat_dict(self, project_root: Path | None = None) -> Dict[str, Any]:
        resolved = str(self.resolve_excel_path(project_root))
        return {
            "excel_path": resolved,
            "days_per_year": self.days_per_year,
            "hours_per_day": self.hours_per_day,
            "strict_single_excel_source": True,
            "strict_no_fallback": True,
            "schema": {
                "date_col": self.schema.date_col,
                "hourly_price_prefix": self.schema.hourly_price_prefix,
                "hour_col_start": self.schema.hour_col_start,
                "hour_col_end": self.schema.hour_col_end,
                "hourly_price_columns": self.schema.hourly_price_columns,
            },
        }


def get_default_tariff_config(excel_path: str) -> TariffConfig:
    """
    显式传入唯一电价表路径。
    不再内置默认电价文件路径，避免隐藏口径。
    """
    return TariffConfig(
        excel_path=excel_path,
        days_per_year=365,
        hours_per_day=24,
    )