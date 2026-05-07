# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Iterable, List

_INITIALIZED = False


def _candidate_font_list() -> List[str]:
    return [
        "Microsoft YaHei", "SimHei", "SimSun",
        "Noto Sans CJK SC", "Source Han Sans SC",
        "WenQuanYi Micro Hei", "Arial Unicode MS",
        "PingFang SC", "Heiti SC", "Arial", "DejaVu Sans",
    ]


def setup_matplotlib_chinese(extra_fonts: Iterable[str] | None = None) -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    import matplotlib.pyplot as plt
    from cycler import cycler

    fonts: List[str] = []
    if extra_fonts is not None:
        fonts.extend([str(x) for x in extra_fonts if str(x).strip()])
    for f in _candidate_font_list():
        if f not in fonts:
            fonts.append(f)

    plt.rcParams["font.sans-serif"] = fonts
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False

    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["figure.max_open_warning"] = 100

    plt.rcParams["figure.dpi"] = 140
    plt.rcParams["savefig.dpi"] = 320
    plt.rcParams["savefig.bbox"] = "tight"
    plt.rcParams["savefig.pad_inches"] = 0.05

    plt.rcParams["axes.linewidth"] = 1.0
    plt.rcParams["lines.linewidth"] = 1.8
    plt.rcParams["lines.markersize"] = 4.0
    plt.rcParams["patch.linewidth"] = 0.8
    plt.rcParams["grid.linewidth"] = 0.55

    plt.rcParams["axes.titlesize"] = 11
    plt.rcParams["axes.titleweight"] = "semibold"
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["xtick.labelsize"] = 9
    plt.rcParams["ytick.labelsize"] = 9
    plt.rcParams["legend.fontsize"] = 8.5
    plt.rcParams["legend.frameon"] = False
    plt.rcParams["legend.borderaxespad"] = 0.6
    plt.rcParams["legend.handlelength"] = 2.2

    plt.rcParams["xtick.direction"] = "in"
    plt.rcParams["ytick.direction"] = "in"
    plt.rcParams["xtick.major.width"] = 0.9
    plt.rcParams["ytick.major.width"] = 0.9
    plt.rcParams["xtick.major.size"] = 4
    plt.rcParams["ytick.major.size"] = 4

    plt.rcParams["axes.grid"] = False
    plt.rcParams["grid.alpha"] = 0.26
    plt.rcParams["grid.linestyle"] = "--"

    palette = [
        "#1f4e79", "#c97b2a", "#3f7f4c", "#8b5e9a", "#b34b4b",
        "#2f6f89", "#6b8e23", "#7a6f9b", "#8c7b6b", "#4c78a8",
    ]
    plt.rcParams["axes.prop_cycle"] = cycler(color=palette)
    plt.rcParams["mathtext.default"] = "regular"

    _INITIALIZED = True


def reset_matplotlib_chinese_flag() -> None:
    global _INITIALIZED
    _INITIALIZED = False
