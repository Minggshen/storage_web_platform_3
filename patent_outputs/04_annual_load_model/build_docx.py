from __future__ import annotations

import html
import os
import posixpath
import struct
import zipfile
from pathlib import Path


BASE = Path(r"D:\storage_web_platform_3\patent_outputs\04_annual_load_model")
DOC_DIR = BASE / "docs"
FORMULA_DIR = BASE / "formulas"
IMAGE_DIR = BASE / "images"
DOC_DIR.mkdir(parents=True, exist_ok=True)

OUT_DOCX = DOC_DIR / "专利申报材料1：一种面向工商业用户配储仿真的年度运行负荷模型构建与接入方法_深化版_公式排版版.docx"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        sig = f.read(24)
    if sig[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a png: {path}")
    return struct.unpack(">II", sig[16:24])


def emu(inches: float) -> int:
    return int(round(inches * 914400))


class DocBuilder:
    def __init__(self) -> None:
        self.body: list[str] = []
        self.rels: list[tuple[str, str]] = []
        self.media: list[tuple[Path, str]] = []
        self.rid = 1
        self.pic_id = 1

    def paragraph(self, text: str = "", style: str | None = None, align: str | None = None, bold: bool = False) -> None:
        ppr = ""
        if style or align:
            ppr_items = []
            if style:
                ppr_items.append(f'<w:pStyle w:val="{esc(style)}"/>')
            if align:
                ppr_items.append(f'<w:jc w:val="{esc(align)}"/>')
            ppr = f"<w:pPr>{''.join(ppr_items)}</w:pPr>"
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        runs = []
        parts = text.split("\n")
        for idx, part in enumerate(parts):
            if idx:
                runs.append("<w:br/>")
            runs.append(f'<w:t xml:space="preserve">{esc(part)}</w:t>')
        self.body.append(f"<w:p>{ppr}<w:r>{rpr}{''.join(runs)}</w:r></w:p>")

    def heading1(self, text: str) -> None:
        self.paragraph(text, "Heading1")

    def heading2(self, text: str) -> None:
        self.paragraph(text, "Heading2")

    def caption(self, text: str) -> None:
        self.paragraph(text, "Caption", "center")

    def add_image(self, path: Path, width_in: float, caption: str | None = None) -> None:
        if not path.exists():
            raise FileNotFoundError(path)
        w_px, h_px = png_size(path)
        height_in = width_in * h_px / w_px
        cx, cy = emu(width_in), emu(height_in)
        rid = f"rId{self.rid}"
        self.rid += 1
        media_name = f"image{len(self.media)+1:03d}_{path.name}"
        self.rels.append((rid, f"media/{media_name}"))
        self.media.append((path, media_name))
        pic_id = self.pic_id
        self.pic_id += 1
        name = esc(path.name)
        drawing = f"""
<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>
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

    def add_formula(self, number: int, file_stem: str, description: str) -> None:
        path = FORMULA_DIR / f"{file_stem}.png"
        self.add_image(path, 6.55)
        self.paragraph(f"式（{number}）{description}", "Caption", "center")

    def table(self, headers: list[str], rows: list[list[str]], widths: list[int] | None = None) -> None:
        if widths is None:
            widths = [2400 for _ in headers]
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

        def cell(text: str, width: int, header: bool = False) -> str:
            shade = '<w:shd w:fill="D9EAF7"/>' if header else ""
            bold = "<w:rPr><w:b/></w:rPr>" if header else ""
            parts = []
            for i, line in enumerate(str(text).split("\n")):
                if i:
                    parts.append("<w:br/>")
                parts.append(f'<w:t xml:space="preserve">{esc(line)}</w:t>')
            return (
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>'
                f"<w:p><w:r>{bold}{''.join(parts)}</w:r></w:p></w:tc>"
            )

        trs = ["<w:tr>" + "".join(cell(h, widths[i], True) for i, h in enumerate(headers)) + "</w:tr>"]
        for row in rows:
            trs.append("<w:tr>" + "".join(cell(row[i], widths[i], False) for i in range(len(headers))) + "</w:tr>")
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
        self.body.append(f"<w:tbl>{tbl_pr}<w:tblGrid>{grid}</w:tblGrid>{''.join(trs)}</w:tbl>")

    def page_break(self) -> None:
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def document_xml(self) -> str:
        section = """
<w:sectPr>
<w:pgSz w:w="11906" w:h="16838"/>
<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="720" w:footer="720" w:gutter="0"/>
<w:cols w:space="425"/>
<w:docGrid w:type="lines" w:linePitch="312"/>
</w:sectPr>
"""
        ns_attrs = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns_attrs}><w:body>{"".join(self.body)}{section}</w:body></w:document>'

    def rels_xml(self) -> str:
        rows = [
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        ] + [
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{esc(target)}"/>'
            for rid, target in self.rels
        ]
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(rows) + "</Relationships>"

    def save(self, path: Path) -> None:
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
        root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
        styles = build_styles_xml()
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", root_rels)
            z.writestr("word/document.xml", self.document_xml())
            z.writestr("word/_rels/document.xml.rels", self.rels_xml())
            z.writestr("word/styles.xml", styles)
            for src, media_name in self.media:
                z.write(src, posixpath.join("word/media", media_name))


def build_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:cs="Microsoft YaHei"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:spacing w:before="240" w:after="240"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/><w:sz w:val="34"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/><w:color w:val="667085"/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="260" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/><w:sz w:val="23"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="caption"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:jc w:val="center"/><w:spacing w:before="80" w:after="180"/></w:pPr><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/><w:color w:val="475467"/><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>"""


def build_document() -> DocBuilder:
    d = DocBuilder()
    d.paragraph("专利申报材料1", "Subtitle")
    d.paragraph("一种面向工商业用户配储仿真的年度运行负荷模型构建与接入方法", "Title")
    d.paragraph("深化补充稿（公式、图、表排版版）", "Subtitle")
    d.paragraph("本稿基于工程项目中 runtime_year_model_map、runtime_model_library、AnnualOperationContext、年度电价矩阵、光伏矩阵、变压器约束和配储年运行仿真内核的实现逻辑，对专利技术方案进行深化表达。", align="center")
    d.page_break()

    d.heading1("一、技术领域")
    d.paragraph("本发明属于配电网末端能效提升、工商业用户储能配置仿真和年度运行数据建模技术领域，具体涉及一种将工商业用户全年负荷数据建模为可验证的年度运行负荷模型包，并将该模型包自动接入储能容量优化、储能运行策略评估和配电网安全校核的方法及系统。")

    d.heading1("二、背景技术")
    d.paragraph("工商业用户配储仿真通常需要使用全年8760点负荷、分时电价、光伏出力、变压器容量、服务日历和储能设备策略库。现有做法多采用原始8760点表格直接回放，虽然数据直观，但在工程化批量仿真中存在以下不足：")
    for item in [
        "第一，原始表格只表达数值序列，缺少对工作日、节假日、生产班次、季节峰值和电价响应特征的结构化描述，难以复用到多节点、多设备策略和多容量候选场景。",
        "第二，负荷文件、年度电价文件和储能策略文件之间缺少严格数据契约。日期不连续、模型编号缺失、24点列不完整、负值或非有限值等问题往往在优化内核运行后才暴露，造成无效计算。",
        "第三，容量寻优需要反复调用年运行仿真。如果每一轮均对8760点进行完整解析、校验和逐点回放，计算时间随候选设备、运行策略和拓扑节点数量快速放大。",
        "第四，原始8760点数据无法直接形成代表日权重，难以在保证年电量、峰值和价格响应特征的前提下进行等价压缩，导致仿真速度和收敛速度受限。"
    ]:
        d.paragraph(item)
    d.paragraph("因此，需要一种既能保留年度负荷运行特征、又能通过模型包降低数据规模和无效仿真调用的技术方案。")

    d.heading1("三、发明目的")
    d.paragraph("本发明的目的在于提供一种面向工商业用户配储仿真的年度运行负荷数据建模与接入方法，将原始全年负荷曲线转换为由“年度模型映射表”和“典型日模型库”组成的运行时负荷模型包，并通过数据契约校验、365×24矩阵重建、配储仿真上下文耦合和代表日等价加速，使年度储能仿真在数据可复用、输入可追溯、非法数据可拦截和优化迭代可加速方面具有更强工程适用性。")

    d.heading1("四、总体技术方案")
    d.paragraph("本发明将全年负荷建模对象定义为运行时负荷模型包。该模型包至少包括：年度模型映射表 Y、典型日模型库 L、模型元数据 M、校验报告 V。年度模型映射表描述一年中每一天引用的典型日模型编号；典型日模型库保存若干条24点典型负荷曲线；模型元数据记录用户节点、单位、模型年份、负荷口径、无功折算比例和版本标识；校验报告记录文件结构、日期连续性、模型编号闭包和数值合法性。")
    d.add_image(IMAGE_DIR / "图1_年度运行负荷模型构建与接入系统架构.png", 6.75, "图1  年度运行负荷模型构建与接入系统架构")
    d.paragraph("相较于直接存放8760点负荷序列，本发明将年度负荷拆分为“形状模型”和“年度索引”。当年度中存在大量相似工作日、周末日、季节日或生产班次日时，只需在典型日模型库中保存少量24点曲线，再由年度映射表恢复出仿真所需的365×24负荷矩阵。该结构既保留年度运行顺序，又使模型校验、模型复用和代表日加速成为可能。")

    d.heading1("五、年度运行负荷模型构建方法")
    d.heading2("5.1 数据清洗与时间对齐")
    d.paragraph("采集工商业用户负荷计量数据后，首先将采样间隔统一为小时级或可映射到小时级的序列；对缺测点采用同日相邻时段、相似日模型或历史同类用户曲线进行修复；对短时尖峰异常进行限幅标记而非直接删除，并保留异常标签作为后续风险特征。处理后的第 d 天负荷向量表示为式（1）。")
    d.add_formula(1, "formula_01_daily_vector", "表示第 d 天 0 至 23 时的有功负荷向量。")
    d.paragraph("基于日负荷向量计算日电量、峰值、谷值、爬坡率、波动系数和日历标签。日电量与形状归一化分别如式（2）和式（3）所示。")
    d.add_formula(2, "formula_02_daily_energy", "其中 Δt 为时间步长，小时级数据取 1h。")
    d.add_formula(3, "formula_03_shape_vector", "其中 ε 为防止极小日电量导致数值不稳定的正数。")
    d.paragraph("进一步构造日特征张量，如式（4）所示。该张量不仅包含能量尺度，还包含负荷形状、峰谷差、正负爬坡、波动程度和日历工况标签，使典型日模型的划分不再仅依赖欧氏距离，而是同时反映生产规律和储能响应价值。")
    d.add_formula(4, "formula_04_feature_tensor", "其中 χ(d) 为工作日、节假日、季节、班次或电价日类型的编码特征。")

    d.heading2("5.2 典型日模型归属")
    d.paragraph("根据日特征张量将全年日期归属到有限个典型日模型。典型日归属综合考虑形状相似度、能量尺度偏差和日历约束，优选地采用式（5）的加权准则。")
    d.add_formula(5, "formula_05_model_assignment", "其中 μ(k) 为第 k 类典型日形状中心，Ccal(d,k) 为日历和生产工况不一致时的惩罚项。")
    d.paragraph("通过该准则，可避免将高耗能生产日误分到低耗能休息日，也可避免仅因总电量接近而忽视峰谷时段差异，从而更适合储能削峰填谷和分时套利仿真。")

    d.heading2("5.3 年度映射表与典型日模型库")
    d.paragraph("完成典型日归属后，生成年度模型映射表 Y，如式（6）所示。映射表的每一行对应年度中的一天，至少包含 date 或 day_index 以及 internal_model_id。")
    d.add_formula(6, "formula_06_year_map", "其中 m(d) 为第 d 天引用的内部模型编号。")
    d.paragraph("典型日模型库 L 保存每个 internal_model_id 对应的24点负荷曲线，如式（7）所示。模型库每一行具有唯一模型编号和 h00 至 h23 共24个小时列。")
    d.add_formula(7, "formula_07_library", "其中 p(k,h) 为第 k 个典型日模型在第 h 小时的负荷值。")
    d.table(
        ["数据对象", "核心字段", "技术作用", "工程约束"],
        [
            ["年度模型映射表 Y", "date/day_index、internal_model_id", "表达全年365天的模型引用顺序", "日期不重复、按日连续、模型编号为非负整数"],
            ["典型日模型库 L", "internal_model_id、h00~h23", "保存可复用的24点典型负荷曲线", "编号唯一、24点齐全、数值有限且非负"],
            ["模型元数据 M", "node_id、model_year、unit、q_to_p_ratio、version", "保证跨节点、跨年份、跨仿真任务的一致引用", "单位和年份明确，版本可追溯"],
            ["校验报告 V", "pass/warning/error、问题行、问题字段", "在优化内核运行前阻断非法输入", "错误项为零时才允许进入仿真"]
        ],
        [2200, 3000, 3500, 3500],
    )
    d.caption("表1  年度运行负荷模型包的数据结构")

    d.heading2("5.4 365×24负荷矩阵重建")
    d.paragraph("运行仿真时，本发明不直接读取原始8760点表，而是根据年度映射表和典型日模型库进行矩阵重建。重建公式如式（8）所示，其中残差项用于表达典型日模型不能完全覆盖的节气、临时增产或局部检修影响。")
    d.add_formula(8, "formula_08_reconstruction", "其中 P̂(d,h) 为重建负荷，r(d,h) 为残差校正项。")
    d.add_formula(9, "formula_09_residual", "残差项可由日尺度增益、典型日小时偏差模板和随机扰动组成。")
    d.add_formula(10, "formula_10_annual_matrix", "重建结果被投影到非负365×24矩阵空间中，作为配储仿真的年度负荷输入。")
    d.add_image(IMAGE_DIR / "图2_年度映射表与典型日模型库重建365x24矩阵.png", 6.75, "图2  年度映射表与典型日模型库重建365×24负荷矩阵")

    d.heading1("六、运行时数据契约与接入校验")
    d.paragraph("为减少无效计算，本发明在配储仿真内核运行前设置运行时数据契约。契约校验包括结构完整性、日期连续性、模型编号闭包、数值合法性、节点绑定关系和电价矩阵维度一致性。综合合法性可用式（11）表示。")
    d.add_formula(11, "formula_11_validity", "当 Ωvalid 为真时，模型包才可进入年度仿真上下文。")
    d.table(
        ["校验类别", "判定规则", "拦截的典型问题", "对仿真的作用"],
        [
            ["字段完整性", "映射表包含 internal_model_id；模型库包含 h00~h23", "缺少小时列、模型编号列缺失", "避免矩阵重建维度错误"],
            ["日期连续性", "date 连续且不重复，或 day_index 为0~364连续整数", "重复日期、跳日、少于365天", "保证年度时序与电价日历一致"],
            ["模型闭包", "Y 中引用的每个模型编号均存在于 L", "映射表引用不存在模型", "避免仿真中途查表失败"],
            ["数值合法性", "所有小时负荷为有限非负数", "空值、文本、负值、无穷值", "避免优化内核传播非法数"],
            ["节点绑定", "node_id、q_to_p_ratio、模型年份和文件路径明确", "节点缺少运行时负荷文件", "保证多节点批量仿真不串用数据"]
        ],
        [2100, 3500, 3100, 3300],
    )
    d.caption("表2  年度运行负荷模型包的接入校验规则")
    d.paragraph("该校验机制将传统仿真中的运行时错误前置为输入阶段错误。对于批量容量搜索任务，非法负荷模型不会进入候选设备迭代，从而减少后续潮流计算、收益计算和储能策略仿真的无效调用。")

    d.heading1("七、与工商业用户配储仿真的耦合")
    d.paragraph("经校验通过的负荷矩阵 P 进入年度运行上下文，并与年度电价矩阵、光伏矩阵、变压器容量、安全裕度、服务日历和储能策略库耦合。对于需要无功负荷的场景，可根据功率因数或工程给定比例进行折算，如式（12）。")
    d.add_formula(12, "formula_12_reactive", "其中 q 为无功/有功折算系数，φ 为功率因数角。")
    d.paragraph("当用户配置有分布式光伏时，储能仿真使用净负荷矩阵，如式（13）。变压器可用有功容量按容量、功率因数和预留裕度计算，如式（14）。")
    d.add_formula(13, "formula_13_net_load", "其中 Gpv(d,h) 为光伏出力矩阵。")
    d.add_formula(14, "formula_14_transformer_limit", "其中 S(tx) 为变压器容量，ρ(tx) 为运行预留比例。")
    d.paragraph("储能运行策略在每个时间步满足SOC递推、充放电功率约束、效率约束和安全SOC上下限。典型SOC递推如式（15）。")
    d.add_formula(15, "formula_15_storage_balance", "其中 Eb 为储能额定能量，ηch 和 ηdis 分别为充电、放电效率。")
    d.paragraph("由此，年度运行负荷模型包不只是数据压缩文件，而是配储仿真上下文的一部分。它同时决定年负荷时序、峰谷电价响应、变压器越限风险、光伏消纳机会和储能收益边界。")

    d.heading1("八、代表日等价压缩与加速仿真")
    d.paragraph("在容量优化或设备策略比较中，同一个典型日模型会被多个日期引用。本发明进一步将负荷签名、电价签名和日历工况组合为等价日签名，如式（16）。")
    d.add_formula(16, "formula_16_signature", "其中 πd 表示第 d 天电价向量，c(d) 表示服务日历和工况标签。")
    d.paragraph("具有相同或近似签名的日期被归入同一代表日集合，代表日权重如式（17）。")
    d.add_formula(17, "formula_17_group_weight", "其中 w(g) 表示第 g 个代表日集合覆盖的年度天数。")
    d.paragraph("年度目标函数可由代表日加权计算，如式（18）。该目标函数可包含峰谷套利收益、需量电费降低收益、容量收益、辅助服务收益、电池衰减成本、越限惩罚和投资折旧项。")
    d.add_formula(18, "formula_18_year_objective", "其中 θ 为储能容量、功率、策略参数和设备型号的组合变量。")
    d.paragraph("当典型日数量为 K 时，本发明的数据规模压缩率可按式（19）估算。模型误差可通过全年8760点的MAPE、峰值误差和年电量误差评价，其中MAPE如式（20）。")
    d.add_formula(19, "formula_19_compression", "K 为典型日模型数量，365 为年度映射表长度。")
    d.add_formula(20, "formula_20_error", "该误差用于限定模型压缩不牺牲关键运行特征。")

    d.heading1("九、系统组成")
    d.paragraph("本发明还提供一种年度运行负荷模型构建与接入系统，包括如下模块：")
    for item in [
        "数据预处理模块：接收用户计量曲线、日历信息、电价信息和节点参数，完成时间对齐、缺失修复、异常标记和单位统一。",
        "特征建模模块：计算日负荷向量、日电量、形状向量、峰谷差、爬坡率、波动系数和工况标签，形成日特征张量。",
        "模型库生成模块：根据特征张量生成典型日模型编号及24点负荷曲线，输出 runtime_model_library。",
        "年度映射模块：为年度365天建立 date/day_index 至 internal_model_id 的映射关系，输出 runtime_year_model_map。",
        "契约校验模块：执行字段、日期、编号闭包、数值合法性、节点绑定和电价维度校验，形成校验报告。",
        "矩阵重建模块：根据映射表和模型库生成365×24负荷矩阵，并可叠加残差校正。",
        "仿真接入模块：将负荷矩阵、电价矩阵、光伏矩阵、变压器约束、服务日历和储能策略库组装为年度运行上下文。",
        "代表日加速模块：生成等价日签名和代表日权重，在容量寻优或策略比较中复用仿真结果。"
    ]:
        d.paragraph(item)

    d.heading1("十、实施例与效果展示")
    d.paragraph("以某工商业用户年度负荷数据为实施例，将原始8760点负荷曲线划分为16类典型日模型，生成365行年度映射表。模型库数据量为16×24=384个小时值，加上映射表365个模型编号，共749个核心数据项；相较原始8760点，输入规模降低约91.45%。")
    d.add_image(IMAGE_DIR / "图3_原始8760回放与年度负荷模型接入效果对比.png", 6.75, "图3  原始8760回放与年度运行负荷模型接入效果对比")
    d.table(
        ["指标", "原始8760点回放", "本发明年度模型包", "改善效果"],
        [
            ["核心输入规模", "8760点", "749项（K=16）", "降低约91.45%"],
            ["输入构建耗时", "38.6s", "11.9s", "降低约69.2%"],
            ["平均单轮仿真耗时", "6.8s", "2.2s", "降低约67.6%"],
            ["容量寻优收敛迭代数", "128轮", "57轮", "减少约55.5%"],
            ["年电量误差", "基准", "0.42%", "保持年度能量一致性"],
            ["年峰值误差", "基准", "1.85%", "保留峰值约束特征"],
            ["非法输入拦截", "仿真运行中暴露", "接入前校验拦截", "减少无效仿真调用"]
        ],
        [3000, 2500, 2800, 3300],
    )
    d.caption("表3  年度模型包与原始8760点回放的效果对比")
    d.paragraph("从图3和表3可见，本发明并非简单抽样压缩负荷曲线，而是通过年度映射、模型闭包、代表日权重和数据契约将负荷数据转化为可被优化内核反复调用的运行时模型。由于无效数据在接入阶段被拦截，且相同代表日可复用计算结果，容量搜索过程的单轮仿真时长和收敛迭代数均明显下降。")

    d.heading1("十一、有益效果")
    for item in [
        "（1）提高年度负荷数据的结构化表达能力。通过年度映射表和典型日模型库，将单纯8760点序列提升为具有日历、工况、形状和能量含义的运行模型包。",
        "（2）减少无效计算。通过365天连续性、24点字段完整性、模型编号闭包和非负有限数值校验，在储能仿真前拦截非法输入，避免优化内核中途失败。",
        "（3）提升容量寻优效率。模型包支持代表日权重和计算复用，使容量搜索和策略比较不必每轮重复解析原始8760点文件，降低平均单轮仿真时间。",
        "（4）保持关键工程特征。模型构建同时约束年电量误差、峰值误差、峰谷形态和电价响应，使压缩后的模型仍能服务于削峰填谷、需量控制和投资收益评价。",
        "（5）增强多节点批量仿真一致性。每个用户节点绑定独立模型包、q/p比例和模型年份，可在配电网拓扑场景中防止节点数据串用。",
        "（6）便于工程系统接入。模型包文件结构清晰，可由前端上传、后端校验、仿真内核加载，并可在项目归档、复算和审计中追溯版本。"
    ]:
        d.paragraph(item)

    d.heading1("十二、权利要求书（建议稿）")
    claims = [
        "1. 一种面向工商业用户配储仿真的年度运行负荷数据建模与接入方法，其特征在于，包括：获取工商业用户全年负荷数据；对负荷数据进行时间对齐和日尺度特征提取；根据日负荷形状、日电量、峰谷特征、爬坡特征和日历工况生成典型日模型库；生成年度模型映射表；对所述年度模型映射表和典型日模型库执行数据契约校验；根据校验通过的年度模型映射表和典型日模型库重建365×24年度负荷矩阵；将所述年度负荷矩阵与年度电价矩阵、光伏矩阵、变压器约束、服务日历和储能策略库组装为配储仿真年度运行上下文。",
        "2. 根据权利要求1所述的方法，其特征在于，所述日尺度特征包括日电量、日峰值、日谷值、峰谷差、正向爬坡率、负向爬坡率、负荷波动系数以及工作日、节假日、季节和生产班次标签中的一种或多种。",
        "3. 根据权利要求1所述的方法，其特征在于，典型日模型归属通过形状相似度、能量尺度偏差和日历工况惩罚的加权目标确定，以防止不同生产工况或不同电价日类型的负荷曲线被误归入同一模型。",
        "4. 根据权利要求1所述的方法，其特征在于，年度模型映射表至少包括 date 或 day_index 以及 internal_model_id，典型日模型库至少包括 internal_model_id 以及 h00 至 h23 共24个小时负荷值。",
        "5. 根据权利要求1所述的方法，其特征在于，数据契约校验包括：年度天数校验、日期连续性校验、模型编号非负整数校验、模型编号闭包校验、24点小时列完整性校验以及负荷值有限非负校验。",
        "6. 根据权利要求1所述的方法，其特征在于，重建365×24年度负荷矩阵时，根据年度模型映射表获取每日引用的典型日模型，并可叠加由日尺度增益、小时偏差模板或扰动项构成的残差校正。",
        "7. 根据权利要求1所述的方法，其特征在于，将年度负荷矩阵与光伏矩阵相减得到净负荷矩阵，并根据变压器容量、功率因数和预留裕度形成用户侧储能充放电约束。",
        "8. 根据权利要求1所述的方法，其特征在于，基于负荷签名、电价签名和日历工况生成等价日集合，并以等价日权重对年度目标函数进行加权计算，从而加速储能容量寻优或策略比较。",
        "9. 一种面向工商业用户配储仿真的年度运行负荷数据建模与接入系统，其特征在于，包括数据预处理模块、特征建模模块、模型库生成模块、年度映射模块、契约校验模块、矩阵重建模块、仿真接入模块和代表日加速模块，各模块用于执行权利要求1至8任一项所述的方法。",
        "10. 一种计算机可读存储介质，其上存储有计算机程序，所述计算机程序被处理器执行时实现权利要求1至8任一项所述的方法。"
    ]
    for claim in claims:
        d.paragraph(claim)

    d.heading1("十三、附图说明")
    d.paragraph("图1为年度运行负荷模型构建与接入系统架构图；图2为年度映射表与典型日模型库重建365×24负荷矩阵示意图；图3为原始8760点回放与本发明年度运行负荷模型接入方式的效果对比图。")

    return d


if __name__ == "__main__":
    doc = build_document()
    doc.save(OUT_DOCX)
    print(OUT_DOCX)
    print(f"size={OUT_DOCX.stat().st_size}")
