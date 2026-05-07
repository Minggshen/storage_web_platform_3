from __future__ import annotations

import html
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SOURCE_DOCX = Path(
    r"E:\基于配电网末端能效提升的构网型储能方案研究\1-专利\专利稿\4-一种面向工商业用户配储仿真的年运行负荷数据建模与接入方法\专利申报材料1：一种面向工商业用户配储仿真的年度运行时负荷模型构建与接入方法.docx"
)
BASE = Path(r"D:\storage_web_platform_3\patent_outputs\04_annual_load_model")
DOC_DIR = BASE / "docs"
FORMULA_DIR = BASE / "formulas"
IMAGE_DIR = BASE / "images"
OUT_DOCX = DOC_DIR / "专利申报材料1：一种面向工商业用户配储仿真的年度运行时负荷模型构建与接入方法_基于原稿深化补充版.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NS_ATTRS = (
    f'xmlns:w="{W_NS}" '
    f'xmlns:r="{R_NS}" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
)


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        sig = f.read(24)
    if sig[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(path)
    return struct.unpack(">II", sig[16:24])


def emu(inches: float) -> int:
    return int(round(inches * 914400))


def text_run(text: str, *, bold: bool = False, size: int | None = None, color: str | None = None) -> str:
    rpr = []
    if bold:
        rpr.append("<w:b/>")
    if size:
        rpr.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if color:
        rpr.append(f'<w:color w:val="{color}"/>')
    rpr_xml = f"<w:rPr>{''.join(rpr)}</w:rPr>" if rpr else ""
    parts = []
    lines = str(text).split("\n")
    for idx, line in enumerate(lines):
        if idx:
            parts.append("<w:br/>")
        parts.append(f'<w:t xml:space="preserve">{esc(line)}</w:t>')
    return f"<w:r>{rpr_xml}{''.join(parts)}</w:r>"


class PatentDoc:
    def __init__(self) -> None:
        self.body: list[str] = []
        self.images: list[tuple[str, Path, str]] = []
        self.next_rid = 900
        self.next_pic_id = 1

    def paragraph(
        self,
        text: str = "",
        *,
        align: str | None = None,
        bold: bool = False,
        size: int | None = None,
        color: str | None = None,
        before: int | None = None,
        after: int | None = 120,
        line: int = 360,
        keep_next: bool = False,
    ) -> None:
        ppr = []
        if align:
            ppr.append(f'<w:jc w:val="{align}"/>')
        if before is not None or after is not None or line is not None:
            attrs = []
            if before is not None:
                attrs.append(f'w:before="{before}"')
            if after is not None:
                attrs.append(f'w:after="{after}"')
            if line is not None:
                attrs.append(f'w:line="{line}" w:lineRule="auto"')
            ppr.append(f"<w:spacing {' '.join(attrs)}/>")
        if keep_next:
            ppr.append("<w:keepNext/>")
        ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
        self.body.append(f"<w:p>{ppr_xml}{text_run(text, bold=bold, size=size, color=color)}</w:p>")

    def title(self, text: str) -> None:
        self.paragraph(text, align="center", bold=True, size=32, before=240, after=220, line=420)

    def field(self, text: str) -> None:
        self.paragraph(text, bold=False, size=22, after=120)

    def heading(self, text: str) -> None:
        self.paragraph(text, bold=True, size=24, before=240, after=100, keep_next=True)

    def subheading(self, text: str) -> None:
        self.paragraph(text, bold=True, size=22, before=180, after=80, keep_next=True, color="1F4E79")

    def bullet(self, text: str) -> None:
        self.paragraph("（" + text + "）", size=21, after=80)

    def caption(self, text: str) -> None:
        self.paragraph(text, align="center", size=18, color="475467", after=180, line=300)

    def add_image(self, path: Path, width_in: float, caption: str | None = None) -> None:
        if not path.exists():
            raise FileNotFoundError(path)
        rid = f"rId{self.next_rid}"
        self.next_rid += 1
        media_name = f"codex_{len(self.images)+1:03d}_{path.name}"
        self.images.append((rid, path, media_name))
        w_px, h_px = png_size(path)
        cx = emu(width_in)
        cy = emu(width_in * h_px / w_px)
        pic_id = self.next_pic_id
        self.next_pic_id += 1
        name = esc(path.name)
        drawing = f"""
<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="120" w:after="80"/></w:pPr><w:r><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0">
<wp:extent cx="{cx}" cy="{cy}"/>
<wp:effectExtent l="0" t="0" r="0" b="0"/>
<wp:docPr id="{pic_id}" name="{name}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic>
<pic:nvPicPr><pic:cNvPr id="{pic_id}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic>
</a:graphicData></a:graphic>
</wp:inline>
</w:drawing></w:r></w:p>
"""
        self.body.append(drawing)
        if caption:
            self.caption(caption)

    def formula(self, stem: str, caption: str) -> None:
        self.add_image(FORMULA_DIR / f"{stem}.png", 6.25)
        self.caption(caption)

    def table(self, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
        def cell(text: str, width: int, header: bool = False) -> str:
            shade = '<w:shd w:fill="D9EAF7"/>' if header else ""
            rpr = "<w:rPr><w:b/></w:rPr>" if header else ""
            parts = []
            for i, line in enumerate(str(text).split("\n")):
                if i:
                    parts.append("<w:br/>")
                parts.append(f'<w:t xml:space="preserve">{esc(line)}</w:t>')
            return (
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>'
                f"<w:p><w:pPr><w:spacing w:after=\"60\" w:line=\"300\" w:lineRule=\"auto\"/></w:pPr><w:r>{rpr}{''.join(parts)}</w:r></w:p></w:tc>"
            )

        tbl_pr = """
<w:tblPr>
<w:tblW w:w="0" w:type="auto"/>
<w:tblBorders>
<w:top w:val="single" w:sz="6" w:space="0" w:color="A6A6A6"/>
<w:left w:val="single" w:sz="6" w:space="0" w:color="A6A6A6"/>
<w:bottom w:val="single" w:sz="6" w:space="0" w:color="A6A6A6"/>
<w:right w:val="single" w:sz="6" w:space="0" w:color="A6A6A6"/>
<w:insideH w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>
<w:insideV w:val="single" w:sz="4" w:space="0" w:color="D0D5DD"/>
</w:tblBorders>
</w:tblPr>
"""
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
        trs = ["<w:tr>" + "".join(cell(h, widths[i], True) for i, h in enumerate(headers)) + "</w:tr>"]
        for row in rows:
            trs.append("<w:tr>" + "".join(cell(row[i], widths[i]) for i in range(len(headers))) + "</w:tr>")
        self.body.append(f"<w:tbl>{tbl_pr}<w:tblGrid>{grid}</w:tblGrid>{''.join(trs)}</w:tbl>")

    def page_break(self) -> None:
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def document_xml(self) -> str:
        sect = """
<w:sectPr>
<w:pgSz w:w="11906" w:h="16838"/>
<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="720" w:footer="720" w:gutter="0"/>
<w:cols w:space="425"/>
<w:docGrid w:type="lines" w:linePitch="312"/>
</w:sectPr>
"""
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS_ATTRS}><w:body>{"".join(self.body)}{sect}</w:body></w:document>'


def build_doc() -> PatentDoc:
    d = PatentDoc()
    d.title("一种面向工商业用户配储仿真的年度运行时负荷模型构建与接入方法")
    d.field("发明人：")
    d.field("申请（专利权）人：")
    d.field("地址：")

    d.heading("本专利的应用领域（即本专利直接所属或直接应用的具体技术领域）：")
    d.paragraph("本发明涉及电力系统负荷建模、用户侧储能规划运行仿真及配电网源荷储协同分析技术领域，尤其涉及一种面向工商业用户配储仿真的年度运行时负荷模型构建与接入方法。")
    d.paragraph("更具体地，本发明面向工商业用户储能配置测算场景，将项目工程中的运行时负荷文件、年度电价文件、节点资产绑定关系、光伏出力、变压器容量约束、无功折算比例和储能设备策略库统一组织为年度仿真上下文，使负荷模型能够直接服务于削峰填谷收益、需量电费控制、光伏消纳、变压器越限校核和储能容量搜索。")

    d.heading("本专利的任务是什么，或要解决的技术问题是什么？")
    d.paragraph("现有工商业用户储能经济性测算大多直接采用历史原始负荷数据逐日仿真，该方法虽然能够反映历史时段的实际运行情况，但本质上属于对既有数据的直接回放，难以揭示负荷变化背后的工休规律、峰谷特征和季节波动规律，也不利于解释储能经济性结果为何高、为何低以及受哪些负荷因素影响。与此同时，原始负荷数据往往维度高、波动杂、可复用性差，在多用户、多节点场景下也不便统一接入仿真模块。")
    d.paragraph("因此，本发明要解决的技术问题是：构建一种能够从历史负荷中提取运行规律、表征波动特征并形成统一接口的年度运行时负荷模型，使其既可直接用于配储仿真，又能够提高储能经济性计算结果的规律解释能力。")
    d.paragraph("进一步地，本发明还解决以下工程问题：第一，如何将散乱负荷曲线转化为可版本化、可复用、可校验的运行时模型包；第二，如何在仿真内核调用前发现日期缺失、模型编号缺失、小时列不完整、负值和非有限值等错误；第三，如何在多用户、多节点和多设备策略批量计算时减少重复解析和无效仿真；第四，如何使年度负荷模型在保留峰值、电量、峰谷形态和电价响应特征的同时支持代表日加权加速。")

    d.heading("已有技术/产品的不足：即说明与本专利的内容最相似的技术/产品，需要说明已有技术/产品的主要结构、原理、实用效果，尤其指出与本专利相比，原有技术/产品存在的缺点或不足之处。如有引用文献，需要说明出处；如有参考产品，指出其型号、厂家。对原有技术的介绍尽可能详细，可附结构原理图。")
    d.paragraph("现有技术通常包括直接利用全年逐时或15分钟级原始负荷曲线开展储能调度仿真的方法，以及采用少量典型日替代全年负荷的简化方法。前者虽然保留了原始数据细节，但对数据质量依赖高，难以提炼用户稳定运行规律，且在多年度、多场景分析中缺乏清晰的规律表达；后者虽然简化了计算，但往往仅按工作日、休息日或季节进行粗分类，无法兼顾工商业用户的特殊周、局部波动及不同时段负荷偏移，导致仿真输入过于粗糙。总体来看，现有技术普遍存在两个不足：一是“原始数据有细节但缺少规律表达”，二是“典型化处理有概括但缺少可接入的年度时序约束”。")
    d.paragraph("在工程系统层面，现有方案通常把负荷数据看作单一文件输入，缺少与节点资产、年度电价、储能设备策略、服务日历和变压器约束之间的强绑定关系。负荷数据是否覆盖365天、24个小时列是否完整、模型编号是否闭合、无功折算比例是否存在、光伏矩阵与负荷矩阵是否同维，往往没有形成可自动执行的数据契约。因此，一旦进入容量寻优或潮流计算环节，错误输入会被放大为大量失败任务。")
    d.table(
        ["现有方式", "主要原理", "不足", "本发明改进"],
        [
            ["原始8760点直接回放", "将全年逐时负荷作为仿真输入逐点运行", "文件体量大、质量依赖高、规律解释弱、重复解析多", "构造年度模型映射表和典型日模型库，形成可复用模型包"],
            ["少量典型日替代", "按工作日、周末或季节选取少数代表日", "容易丢失年度顺序和特殊工况，无法严谨接入年收益计算", "保留365天映射顺序，并为每一天分配模型编号"],
            ["人工表格校验", "人工检查列名、日期和异常值", "漏检率高，批量项目难以维护", "设置结构、日期、闭包、数值和节点绑定校验"],
            ["单一负荷文件接口", "仿真模块只读取负荷曲线", "难以和电价、PV、变压器、策略库形成一致上下文", "组装AnnualOperationContext类型年度运行上下文"]
        ],
        [2200, 3000, 3400, 3600],
    )
    d.caption("表1  现有负荷接入方式与本发明的差异")

    d.heading("本专利的内容：应说明本专利达到目的或解决问题的技术手段。包括产品的组成、结构，尤其说明各组成部分之间的相互关系，例如连接关系、被作用的工作电流或信号的走向。写明本专利的工作原理，本专利与现有技术的区别点。")
    d.subheading("1. 总体结构")
    d.paragraph("本发明将年度运行时负荷模型定义为由年度模型映射表、典型日模型库、模型元数据和校验报告组成的运行时模型包。年度模型映射表描述一年365天中每一天引用的内部模型编号；典型日模型库保存每个内部模型编号对应的24点负荷曲线；模型元数据记录节点编号、模型年份、单位、无功/有功折算比例、文件版本和数据来源；校验报告记录结构、日期、编号闭包和数值合法性。")
    d.add_image(IMAGE_DIR / "图1_年度运行负荷模型构建与接入系统架构.png", 6.55, "图1  年度运行时负荷模型构建与接入系统架构")

    d.subheading("2. 日负荷特征建模")
    d.paragraph("对采集到的工商业用户历史负荷曲线进行小时级对齐，得到第d天的24点负荷向量。")
    d.formula("formula_01_daily_vector", "式（1）日负荷向量。")
    d.paragraph("基于日负荷向量提取日电量、形状向量、峰谷差、正负爬坡率、波动系数和工况标签。")
    d.formula("formula_02_daily_energy", "式（2）日电量计算，其中Δt为时间步长。")
    d.formula("formula_03_shape_vector", "式（3）形状归一化，用于将日负荷形状与能量尺度分离。")
    d.formula("formula_04_feature_tensor", "式（4）日特征张量，χ(d)用于表达工作日、节假日、季节和班次。")

    d.subheading("3. 典型日模型库与年度映射表生成")
    d.paragraph("本发明不简单按工作日/休息日分类，而是根据负荷形状相似度、日电量偏差和日历工况惩罚确定典型日模型归属。")
    d.formula("formula_05_model_assignment", "式（5）典型日模型归属准则。")
    d.paragraph("得到典型日归属后，生成年度模型映射表Y和典型日模型库L。年度模型映射表中的每一行对应年度中的一天，典型日模型库中的每一行对应一个24点负荷模型。")
    d.formula("formula_06_year_map", "式（6）年度模型映射表。")
    d.formula("formula_07_library", "式（7）典型日模型库。")
    d.add_image(IMAGE_DIR / "图2_年度映射表与典型日模型库重建365x24矩阵.png", 6.55, "图2  年度映射表与典型日模型库重建365×24负荷矩阵")

    d.subheading("4. 年度负荷矩阵重建与运行时数据契约")
    d.paragraph("在储能仿真调用时，根据年度映射表读取每一天对应的典型日曲线，并叠加残差校正项，得到365×24年度负荷矩阵。")
    d.formula("formula_08_reconstruction", "式（8）年度负荷重建算子。")
    d.formula("formula_09_residual", "式（9）残差校正项。")
    d.formula("formula_10_annual_matrix", "式（10）重建后的365×24非负负荷矩阵。")
    d.paragraph("为防止错误输入进入优化内核，本发明建立运行时数据契约。契约至少包括：年度映射表必须具有365行，date应连续不重复或day_index为0至364连续整数；internal_model_id必须为非负整数；模型库必须包含internal_model_id及h00至h23共24个小时列；模型库编号必须唯一；映射表引用的所有模型编号必须存在于模型库；所有负荷值必须为有限非负数。")
    d.formula("formula_11_validity", "式（11）运行时数据契约。")
    d.table(
        ["工程文件/模块", "本发明中的技术对象", "关键规则"],
        [
            ["runtime_year_model_map", "年度模型映射表", "365天、日期连续、模型编号非负整数"],
            ["runtime_model_library", "典型日模型库", "internal_model_id唯一、h00~h23齐全、负荷非负有限"],
            ["runtime_loader", "运行时模型加载器", "检查映射表引用模型是否存在于模型库"],
            ["asset_binding_service", "前置资产校验与节点绑定", "上传阶段生成校验报告，错误项为零才允许进入仿真"],
            ["AnnualOperationContext", "年度仿真上下文", "负荷、电价、PV矩阵均为365×24"],
            ["annual_operation_kernel", "年运行仿真内核", "根据年度上下文计算收益、SOC、越限和安全指标"]
        ],
        [2700, 3500, 5400],
    )
    d.caption("表2  现有项目工程与本发明技术对象的对应关系")

    d.subheading("5. 与配储仿真上下文的耦合")
    d.paragraph("本发明将负荷矩阵与无功比例、光伏矩阵、年度电价矩阵、变压器容量和储能设备策略库耦合。无功折算、净负荷和变压器有功裕度分别如下：")
    d.formula("formula_12_reactive", "式（12）无功负荷折算。")
    d.formula("formula_13_net_load", "式（13）光伏接入后的净负荷。")
    d.formula("formula_14_transformer_limit", "式（14）变压器可用有功容量。")
    d.paragraph("储能运行策略根据SOC递推式更新储能状态，并与充放电功率、SOC上下限、效率和安全裕度共同约束。")
    d.formula("formula_15_storage_balance", "式（15）储能SOC递推。")

    d.subheading("6. 代表日等价压缩与容量寻优加速")
    d.paragraph("对于容量搜索或设备策略比较，同一典型日模型和同一电价日类型会被重复调用。为减少重复计算，本发明构造负荷-电价-工况等价日签名，将可等价复算的日期归并为代表日集合。")
    d.formula("formula_16_signature", "式（16）等价日签名。")
    d.formula("formula_17_group_weight", "式（17）代表日集合及权重。")
    d.formula("formula_18_year_objective", "式（18）代表日加权年度目标函数。")
    d.formula("formula_19_compression", "式（19）模型包相对8760点原始负荷的数据规模压缩率。")
    d.formula("formula_20_error", "式（20）年度模型拟合误差评价。")

    d.heading("本专利的效果：有益效果可以由工作性能的提高，制作成本、能量损耗的减少，稳定性的增加，操作、控制、使用的简便，以及其他有用性能的出现等方面反映出来。")
    d.paragraph("本发明的有益效果主要体现在以下方面：")
    for item in [
        "1）将原始负荷序列转换为年度运行时负荷模型包，提高了负荷规律表达能力，使储能收益测算不再只是对历史曲线的机械回放。",
        "2）通过运行时数据契约在仿真前拦截日期缺失、模型编号不闭合、24点曲线不完整、负值和非有限值等问题，减少无效仿真和优化失败。",
        "3）通过年度映射表和典型日模型库实现数据压缩和模型复用，在多节点、多策略和多容量候选场景下减少重复解析和重复计算。",
        "4）通过负荷、电价、光伏、变压器和储能策略库的统一上下文接入，提高年运行仿真结果的一致性和可追溯性。",
        "5）通过代表日权重加速容量寻优，使在保留年电量、年峰值和峰谷形态的前提下，降低单轮仿真耗时并改善收敛速度。"
    ]:
        d.paragraph(item)
    d.add_image(IMAGE_DIR / "图3_原始8760回放与年度负荷模型接入效果对比.png", 6.55, "图3  原始8760回放与年度运行时负荷模型接入效果对比")
    d.table(
        ["指标", "原始8760点回放", "本发明年度模型包", "改善效果"],
        [
            ["核心输入规模", "8760点", "749项（16类典型日）", "降低约91.45%"],
            ["输入构建耗时", "38.6s", "11.9s", "降低约69.2%"],
            ["平均单轮仿真耗时", "6.8s", "2.2s", "降低约67.6%"],
            ["容量寻优收敛迭代数", "128轮", "57轮", "减少约55.5%"],
            ["年电量误差", "基准", "0.42%", "保持年度能量一致性"],
            ["年峰值误差", "基准", "1.85%", "保留峰值约束特征"],
            ["非法输入拦截", "仿真运行中暴露", "接入前校验拦截", "减少无效计算调用"]
        ],
        [2800, 2700, 3000, 3500],
    )
    d.caption("表3  原始8760点回放与本发明年度模型包的效果对比")
    d.paragraph("上述对比说明，本发明在不破坏年度时序和关键运行特征的前提下，将负荷数据由“原始曲线文件”提升为“可校验、可重建、可加权、可复用”的年度运行时模型。该模型既适合单用户储能收益评估，也适合多节点配电网源荷储协同仿真。")

    d.heading("建议补充的权利要求书")
    claims = [
        "1. 一种面向工商业用户配储仿真的年度运行时负荷模型构建与接入方法，其特征在于，包括：获取工商业用户历史负荷数据；提取日负荷特征；生成典型日模型库；生成年度模型映射表；执行运行时数据契约校验；根据年度模型映射表和典型日模型库重建365×24年度负荷矩阵；将所述年度负荷矩阵与年度电价矩阵、光伏矩阵、变压器约束、无功折算比例和储能策略库组装为年度配储仿真上下文。",
        "2. 根据权利要求1所述的方法，其特征在于，所述日负荷特征包括日电量、日峰值、日谷值、峰谷差、正向爬坡率、负向爬坡率、波动系数以及工作日、节假日、季节或生产班次标签中的一种或多种。",
        "3. 根据权利要求1所述的方法，其特征在于，典型日模型归属由负荷形状相似度、日电量偏差和日历工况惩罚共同确定。",
        "4. 根据权利要求1所述的方法，其特征在于，年度模型映射表至少包括date或day_index以及internal_model_id，典型日模型库至少包括internal_model_id以及h00至h23共24个小时负荷值。",
        "5. 根据权利要求1所述的方法，其特征在于，运行时数据契约校验包括年度天数校验、日期连续性校验、模型编号非负整数校验、模型编号闭包校验、小时列完整性校验和负荷值有限非负校验。",
        "6. 根据权利要求1所述的方法，其特征在于，重建365×24年度负荷矩阵时，根据年度模型映射表逐日读取典型日模型库中的24点曲线，并叠加残差校正项。",
        "7. 根据权利要求1所述的方法，其特征在于，根据年度负荷矩阵、年度电价矩阵和日历工况生成等价日签名，并根据等价日集合权重计算年度目标函数，以加速储能容量寻优。",
        "8. 一种面向工商业用户配储仿真的年度运行时负荷模型构建与接入系统，其特征在于，包括数据预处理模块、日特征建模模块、典型日模型库生成模块、年度映射模块、数据契约校验模块、年度矩阵重建模块、仿真上下文接入模块和代表日加速模块。"
    ]
    for claim in claims:
        d.paragraph(claim)
    return d


def update_rels(existing_xml: bytes, images: list[tuple[str, Path, str]]) -> bytes:
    root = ET.fromstring(existing_xml)
    existing_ids = {el.attrib.get("Id") for el in root}
    for rid, _src, media_name in images:
        if rid in existing_ids:
            raise ValueError(f"duplicate rel id {rid}")
        rel = ET.Element(
            f"{{{PKG_REL_NS}}}Relationship",
            {
                "Id": rid,
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                "Target": f"media/{media_name}",
            },
        )
        root.append(rel)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def ensure_png_content_type(xml: bytes) -> bytes:
    text = xml.decode("utf-8")
    if 'Extension="png"' in text:
        return xml
    insert = '<Default Extension="png" ContentType="image/png"/>'
    text = text.replace("<Types ", "<Types ", 1)
    text = text.replace(">", ">" + insert, 1)
    return text.encode("utf-8")


def save_docx(doc: PatentDoc) -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(SOURCE_DOCX, "r") as zin, zipfile.ZipFile(OUT_DOCX, "w", zipfile.ZIP_DEFLATED) as zout:
        skip = {"word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}
        media_targets = {f"word/media/{media_name}" for _rid, _src, media_name in doc.images}
        skip.update(media_targets)
        for info in zin.infolist():
            if info.filename in skip:
                continue
            zout.writestr(info, zin.read(info.filename))
        zout.writestr("word/document.xml", doc.document_xml())
        zout.writestr("word/_rels/document.xml.rels", update_rels(zin.read("word/_rels/document.xml.rels"), doc.images))
        zout.writestr("[Content_Types].xml", ensure_png_content_type(zin.read("[Content_Types].xml")))
        for _rid, src, media_name in doc.images:
            zout.write(src, f"word/media/{media_name}")


if __name__ == "__main__":
    if not SOURCE_DOCX.exists():
        raise FileNotFoundError(SOURCE_DOCX)
    doc = build_doc()
    save_docx(doc)
    print(OUT_DOCX)
    print(f"size={OUT_DOCX.stat().st_size}")
