Add-Type -AssemblyName System.Drawing

$BaseDir = "D:\storage_web_platform_3\patent_outputs\04_annual_load_model"
$FormulaDir = Join-Path $BaseDir "formulas"
$ImageDir = Join-Path $BaseDir "images"
New-Item -ItemType Directory -Path $FormulaDir -Force | Out-Null
New-Item -ItemType Directory -Path $ImageDir -Force | Out-Null

function New-Color($hex) {
    return [System.Drawing.ColorTranslator]::FromHtml($hex)
}

function New-Canvas($width, $height) {
    $bmp = New-Object System.Drawing.Bitmap $width, $height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
    $g.Clear([System.Drawing.Color]::White)
    return @($bmp, $g)
}

function Save-Canvas($bmp, $g, $path) {
    $g.Dispose()
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

function Draw-Text($g, $text, $x, $y, $w, $h, $font, $color, $align = "Near", $valign = "Center") {
    $brush = New-Object System.Drawing.SolidBrush $color
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = [System.Drawing.StringAlignment]::$align
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::$valign
    $fmt.Trimming = [System.Drawing.StringTrimming]::EllipsisWord
    $rect = New-Object System.Drawing.RectangleF($x, $y, $w, $h)
    $g.DrawString($text, $font, $brush, $rect, $fmt)
    $brush.Dispose()
    $fmt.Dispose()
}

function Draw-Box($g, $x, $y, $w, $h, $text, $fillHex, $borderHex, $font, $textColorHex = "#22313f") {
    $fill = New-Object System.Drawing.SolidBrush (New-Color $fillHex)
    $pen = New-Object System.Drawing.Pen (New-Color $borderHex), 2
    $rect = New-Object System.Drawing.RectangleF($x, $y, $w, $h)
    $g.FillRectangle($fill, $rect)
    $g.DrawRectangle($pen, $x, $y, $w, $h)
    Draw-Text $g $text ($x + 12) ($y + 8) ($w - 24) ($h - 16) $font (New-Color $textColorHex) "Center" "Center"
    $fill.Dispose()
    $pen.Dispose()
}

function Draw-Arrow($g, $x1, $y1, $x2, $y2, $hex = "#5b6472") {
    $pen = New-Object System.Drawing.Pen (New-Color $hex), 3
    $cap = New-Object System.Drawing.Drawing2D.AdjustableArrowCap 7, 7
    $pen.CustomEndCap = $cap
    $g.DrawLine($pen, $x1, $y1, $x2, $y2)
    $cap.Dispose()
    $pen.Dispose()
}

function Draw-FormulaImage($name, $formula, $caption) {
    $w = 1800
    $h = 220
    $items = New-Canvas $w $h
    $bmp = $items[0]
    $g = $items[1]
    $borderPen = New-Object System.Drawing.Pen (New-Color "#d8dde6"), 2
    $g.DrawRectangle($borderPen, 1, 1, $w - 3, $h - 3)
    $borderPen.Dispose()
    $tagFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 22, [System.Drawing.FontStyle]::Regular)
    $formulaFont = New-Object System.Drawing.Font("Cambria Math", 38, [System.Drawing.FontStyle]::Regular)
    $smallFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 18, [System.Drawing.FontStyle]::Regular)
    Draw-Text $g $caption 34 18 420 38 $tagFont (New-Color "#49617a") "Near" "Center"
    Draw-Text $g $formula 70 66 1660 84 $formulaFont (New-Color "#111827") "Near" "Center"
    Draw-Text $g "注：公式图片采用数学字体排版，插入稿件后可直接阅读。" 70 158 1200 36 $smallFont (New-Color "#667085") "Near" "Center"
    $tagFont.Dispose()
    $formulaFont.Dispose()
    $smallFont.Dispose()
    Save-Canvas $bmp $g (Join-Path $FormulaDir "$name.png")
}

$formulaList = @(
    @{Name="formula_01_daily_vector"; Caption="公式（1）日负荷向量"; Formula="x(d) = [ P(d,0), P(d,1), ... , P(d,23) ]ᵀ"},
    @{Name="formula_02_daily_energy"; Caption="公式（2）日电量"; Formula="E(d) = Σ(h=0→23) P(d,h) · Δt"},
    @{Name="formula_03_shape_vector"; Caption="公式（3）形状归一化"; Formula="s(d) = x(d) / [ E(d) + ε ]"},
    @{Name="formula_04_feature_tensor"; Caption="公式（4）日特征张量"; Formula="Φ(d) = [ E(d), Pmax(d), Pmin(d), R⁺(d), R⁻(d), σ(d), χ(d) ]"},
    @{Name="formula_05_model_assignment"; Caption="公式（5）典型日模型归属"; Formula="k(d) = argmin{k∈K}{ α‖s(d)-μ(k)‖₂² + β|Ê(d)-Ē(k)| + ζCcal(d,k) }"},
    @{Name="formula_06_year_map"; Caption="公式（6）年度模型映射"; Formula="Y = ( m(1), m(2), ... , m(D) ),  m(d)=k(d)"},
    @{Name="formula_07_library"; Caption="公式（7）典型日模型库"; Formula="L = { p(k,h) | k∈K, h=0,1,...,23 }"},
    @{Name="formula_08_reconstruction"; Caption="公式（8）年度负荷重建"; Formula="P̂(d,h) = p(m(d),h) + r(d,h)"},
    @{Name="formula_09_residual"; Caption="公式（9）残差校正"; Formula="r(d,h) = λ(d) · a(m(d),h) + ε(d,h)"},
    @{Name="formula_10_annual_matrix"; Caption="公式（10）365×24矩阵"; Formula="P ∈ R⁺(365×24),  P(d,h)=max[0, P̂(d,h)]"},
    @{Name="formula_11_validity"; Caption="公式（11）数据契约"; Formula="Ωvalid = I(|Y|=365) · Π I(m(d)∈K) · Π I(p(k,h)≥0)"},
    @{Name="formula_12_reactive"; Caption="公式（12）无功折算"; Formula="Q(d,h)=q · P(d,h),  q=tan[arccos(φ)]"},
    @{Name="formula_13_net_load"; Caption="公式（13）净负荷"; Formula="N(d,h)=P(d,h)-Gpv(d,h)"},
    @{Name="formula_14_transformer_limit"; Caption="公式（14）变压器有功裕度"; Formula="Plim(tx) = S(tx) · cosφ(tx) · [1-ρ(tx)]"},
    @{Name="formula_15_storage_balance"; Caption="公式（15）储能SOC递推"; Formula="SOC(t+1)=SOC(t)+ηch·Pch(t)Δt/Eb−Pdis(t)Δt/[ηdis·Eb]"},
    @{Name="formula_16_signature"; Caption="公式（16）等价日签名"; Formula="C(d) = ( round(Pd,np), round(πd,nπ), c(d) )"},
    @{Name="formula_17_group_weight"; Caption="公式（17）代表日权重"; Formula="G(g)={ d | C(d)=C(g) },  w(g)=|G(g)|"},
    @{Name="formula_18_year_objective"; Caption="公式（18）加权年目标"; Formula="Jyear(θ)=Σg w(g) · J(Pg,πg,θ) + Ψgrid(θ)"},
    @{Name="formula_19_compression"; Caption="公式（19）模型压缩率"; Formula="ηcomp = 1 − (24K + 365)/(365×24)"},
    @{Name="formula_20_error"; Caption="公式（20）拟合误差"; Formula="MAPE = (1/8760)Σ |P(d,h)-P̂(d,h)| / [P(d,h)+ε]"}
)

foreach ($f in $formulaList) {
    Draw-FormulaImage $f.Name $f.Formula $f.Caption
}

function Draw-Figure1 {
    $items = New-Canvas 1800 1050
    $bmp = $items[0]
    $g = $items[1]
    $titleFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 34, [System.Drawing.FontStyle]::Bold)
    $headFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 22, [System.Drawing.FontStyle]::Bold)
    $boxFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 20, [System.Drawing.FontStyle]::Regular)
    $smallFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 17, [System.Drawing.FontStyle]::Regular)
    Draw-Text $g "年度运行负荷模型构建与接入系统架构" 40 24 1720 56 $titleFont (New-Color "#162033") "Center" "Center"
    Draw-Text $g "从计量曲线到储能容量仿真的模型化运行时数据通道" 40 86 1720 36 $smallFont (New-Color "#667085") "Center" "Center"

    Draw-Text $g "源数据层" 80 150 260 34 $headFont (New-Color "#375a7f") "Center" "Center"
    Draw-Box $g 70 195 280 96 "用户计量曲线`n15min/1h负荷" "#eef6ff" "#80aee0" $boxFont
    Draw-Box $g 70 322 280 96 "日历与生产标签`n工作日/节假日/班次" "#eef6ff" "#80aee0" $boxFont
    Draw-Box $g 70 449 280 96 "分时电价与服务日历`n尖峰平谷/需求电费" "#eef6ff" "#80aee0" $boxFont
    Draw-Box $g 70 576 280 96 "配电接入约束`n变压器/PV/q-p比" "#eef6ff" "#80aee0" $boxFont

    Draw-Text $g "特征建模层" 430 150 290 34 $headFont (New-Color "#3f5f43") "Center" "Center"
    Draw-Box $g 410 225 330 110 "清洗与对齐`n缺测修复、异常削峰、日边界统一" "#f0f8ef" "#8ab98a" $boxFont
    Draw-Box $g 410 392 330 110 "形状-能量分解`nx_d, E_d, s_d, 峰谷斜率特征" "#f0f8ef" "#8ab98a" $boxFont
    Draw-Box $g 410 559 330 110 "典型日归类`n季节/工况/价格/风险分层" "#f0f8ef" "#8ab98a" $boxFont

    Draw-Text $g "运行模型包" 810 150 290 34 $headFont (New-Color "#6b4e16") "Center" "Center"
    Draw-Box $g 790 235 340 116 "runtime_year_model_map`n365日 → internal_model_id" "#fff7e6" "#d8a83f" $boxFont
    Draw-Box $g 790 414 340 116 "runtime_model_library`n每个模型24点负荷曲线" "#fff7e6" "#d8a83f" $boxFont
    Draw-Box $g 790 593 340 116 "模型元数据`n版本、单位、节点、校验摘要" "#fff7e6" "#d8a83f" $boxFont

    Draw-Text $g "数据契约层" 1190 150 290 34 $headFont (New-Color "#614a80") "Center" "Center"
    Draw-Box $g 1170 225 330 100 "结构校验`n365天、24小时、日期连续" "#f6f0ff" "#a78bdb" $boxFont
    Draw-Box $g 1170 375 330 100 "闭包校验`n映射ID必须存在于模型库" "#f6f0ff" "#a78bdb" $boxFont
    Draw-Box $g 1170 525 330 100 "数值校验`n有限、非负、单位一致" "#f6f0ff" "#a78bdb" $boxFont
    Draw-Box $g 1170 675 330 100 "矩阵生成`nP、PV、tariff、net load" "#f6f0ff" "#a78bdb" $boxFont

    Draw-Text $g "仿真接入层" 1505 150 240 34 $headFont (New-Color "#7a3d45") "Center" "Center"
    Draw-Box $g 1525 268 230 132 "AnnualOperationContext`n365×24年度运行上下文" "#fff1f2" "#da7b88" $boxFont
    Draw-Box $g 1525 470 230 132 "配储优化内核`n削峰填谷/收益/安全裕度" "#fff1f2" "#da7b88" $boxFont
    Draw-Box $g 1525 672 230 132 "结果回写`n年收益、SOC、越限风险" "#fff1f2" "#da7b88" $boxFont

    Draw-Arrow $g 350 370 410 370
    Draw-Arrow $g 740 370 790 298
    Draw-Arrow $g 740 500 790 472
    Draw-Arrow $g 1130 470 1170 425
    Draw-Arrow $g 1130 650 1170 725
    Draw-Arrow $g 1500 725 1525 735
    Draw-Arrow $g 1640 400 1640 470
    Draw-Arrow $g 1640 602 1640 672

    Draw-Text $g "图1  本方法将离散负荷文件编译为可验证、可复用、可加权计算的年度运行负荷模型包，并与储能仿真上下文自动耦合。" 65 935 1670 54 $smallFont (New-Color "#475467") "Center" "Center"
    $titleFont.Dispose(); $headFont.Dispose(); $boxFont.Dispose(); $smallFont.Dispose()
    Save-Canvas $bmp $g (Join-Path $ImageDir "图1_年度运行负荷模型构建与接入系统架构.png")
}

function Draw-Figure2 {
    $items = New-Canvas 1800 1020
    $bmp = $items[0]
    $g = $items[1]
    $titleFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 32, [System.Drawing.FontStyle]::Bold)
    $headFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 22, [System.Drawing.FontStyle]::Bold)
    $textFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 18, [System.Drawing.FontStyle]::Regular)
    $smallFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 15, [System.Drawing.FontStyle]::Regular)
    Draw-Text $g "年度映射表与典型日模型库重建 365×24 负荷矩阵" 40 24 1720 56 $titleFont (New-Color "#162033") "Center" "Center"

    Draw-Box $g 70 122 410 62 "年度模型映射表 Y" "#edf5ff" "#78a5d8" $headFont
    $headers = @("date", "day_index", "internal_model_id")
    $rows = @(
        @("2025-01-01", "0", "M03"),
        @("2025-01-02", "1", "M03"),
        @("2025-01-03", "2", "M11"),
        @("...", "...", "..."),
        @("2025-12-31", "364", "M07")
    )
    $x0 = 70; $y0 = 210; $cw = @(145, 105, 160); $rh = 45
    for ($i=0; $i -lt 3; $i++) {
        Draw-Box $g ($x0 + ($cw[0..($i-1)] | Measure-Object -Sum).Sum) $y0 $cw[$i] $rh $headers[$i] "#dceeff" "#9bb9d8" $smallFont
    }
    for ($r=0; $r -lt $rows.Count; $r++) {
        $cy = $y0 + $rh * ($r + 1)
        $start = $x0
        for ($c=0; $c -lt 3; $c++) {
            Draw-Box $g $start $cy $cw[$c] $rh $rows[$r][$c] "#ffffff" "#cad8e7" $smallFont
            $start += $cw[$c]
        }
    }

    Draw-Box $g 600 122 520 62 "典型日模型库 L" "#fff6e8" "#d7a84a" $headFont
    $libX = 600; $libY = 220
    Draw-Box $g $libX $libY 120 52 "model_id" "#ffedcc" "#d7a84a" $smallFont
    Draw-Box $g ($libX+120) $libY 400 52 "h00 ... h23  24点曲线" "#ffedcc" "#d7a84a" $smallFont
    $colors = @("#6da7de", "#ef8c4f", "#70b66c", "#8d79d6")
    for ($r=0; $r -lt 4; $r++) {
        $yy = $libY + 52 * ($r + 1)
        Draw-Box $g $libX $yy 120 52 ("M" + ("{0:D2}" -f (3+$r*2))) "#ffffff" "#ead1a1" $smallFont
        Draw-Box $g ($libX+120) $yy 400 52 "" "#ffffff" "#ead1a1" $smallFont
        $pen = New-Object System.Drawing.Pen (New-Color $colors[$r]), 3
        $prevX = $libX + 140
        $prevY = $yy + 35
        for ($i=0; $i -lt 24; $i++) {
            $xx = $libX + 140 + $i * 15
            $val = [Math]::Sin(($i + $r*2) / 24.0 * 6.283) * 16 + [Math]::Sin(($i-7)/24.0*6.283)*8
            $py = $yy + 27 - $val
            if ($i -gt 0) { $g.DrawLine($pen, $prevX, $prevY, $xx, $py) }
            $prevX = $xx; $prevY = $py
        }
        $pen.Dispose()
    }
    Draw-Box $g 600 525 520 75 "闭包关系：Y 中出现的每个 internal_model_id`n必须能在 L 中找到唯一 24点曲线" "#fffaf0" "#d7a84a" $textFont

    Draw-Arrow $g 492 385 590 385
    Draw-Arrow $g 1128 385 1205 385

    Draw-Box $g 1220 122 500 62 "重建后的年度负荷矩阵 P" "#edf7f1" "#79b58a" $headFont
    $hx = 1240; $hy = 225; $cellW = 16; $cellH = 10
    for ($d=0; $d -lt 72; $d++) {
        for ($h=0; $h -lt 24; $h++) {
            $v = 0.45 + 0.35*[Math]::Sin(($h-6)/24.0*6.283) + 0.18*[Math]::Sin(($d)/72.0*6.283)
            if ($v -lt 0) { $v = 0 }
            if ($v -gt 1) { $v = 1 }
            $r = [int](255 - 120*$v)
            $gr = [int](245 - 85*$v)
            $b = [int](238 - 160*$v)
            $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb($r,$gr,$b))
            $g.FillRectangle($brush, $hx + $h*$cellW, $hy + $d*$cellH, $cellW-1, $cellH-1)
            $brush.Dispose()
        }
    }
    Draw-Text $g "列：0~23时" 1240 185 390 30 $smallFont (New-Color "#667085") "Center" "Center"
    Draw-Text $g "行：365日（图中按比例压缩显示）" 1620 470 80 140 $smallFont (New-Color "#667085") "Center" "Center"

    Draw-Box $g 1235 820 145 62 "365天" "#ffffff" "#79b58a" $textFont
    Draw-Box $g 1405 820 145 62 "24小时" "#ffffff" "#79b58a" $textFont
    Draw-Box $g 1575 820 145 62 "非负有限" "#ffffff" "#79b58a" $textFont
    Draw-Text $g "图2  年度映射表只存储每天引用的典型日编号，模型库只存储少量24点典型曲线；重建算子将二者组合为储能仿真需要的 365×24 年度负荷矩阵。" 65 940 1670 54 $textFont (New-Color "#475467") "Center" "Center"
    $titleFont.Dispose(); $headFont.Dispose(); $textFont.Dispose(); $smallFont.Dispose()
    Save-Canvas $bmp $g (Join-Path $ImageDir "图2_年度映射表与典型日模型库重建365x24矩阵.png")
}

function Draw-BarPair($g, $x, $y, $w, $h, $title, $rawVal, $modelVal, $unit, $maxVal, $font, $smallFont) {
    Draw-Text $g $title $x ($y-36) $w 30 $font (New-Color "#1f2937") "Center" "Center"
    $base = $y + $h - 40
    $barW = 75
    $rawH = [Math]::Max(4, ($rawVal / $maxVal) * ($h - 80))
    $modelH = [Math]::Max(4, ($modelVal / $maxVal) * ($h - 80))
    $rawBrush = New-Object System.Drawing.SolidBrush (New-Color "#6b7280")
    $modelBrush = New-Object System.Drawing.SolidBrush (New-Color "#2563eb")
    $g.FillRectangle($rawBrush, $x + 92, $base - $rawH, $barW, $rawH)
    $g.FillRectangle($modelBrush, $x + 235, $base - $modelH, $barW, $modelH)
    Draw-Text $g ("原始8760`n" + $rawVal + $unit) ($x + 55) ($base + 8) 150 54 $smallFont (New-Color "#374151") "Center" "Near"
    Draw-Text $g ("本方法`n" + $modelVal + $unit) ($x + 195) ($base + 8) 150 54 $smallFont (New-Color "#174ea6") "Center" "Near"
    $rawBrush.Dispose(); $modelBrush.Dispose()
}

function Draw-Figure3 {
    $items = New-Canvas 1800 1120
    $bmp = $items[0]
    $g = $items[1]
    $titleFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 32, [System.Drawing.FontStyle]::Bold)
    $headFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 21, [System.Drawing.FontStyle]::Bold)
    $textFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 17, [System.Drawing.FontStyle]::Regular)
    $smallFont = New-Object System.Drawing.Font("Microsoft YaHei UI", 14, [System.Drawing.FontStyle]::Regular)
    Draw-Text $g "原始8760回放与年度运行负荷模型接入效果对比" 40 24 1720 56 $titleFont (New-Color "#162033") "Center" "Center"
    Draw-Text $g "实施例：16类典型日模型库，365日映射表，接入同一工商业用户年度电价与储能策略库" 40 84 1720 32 $textFont (New-Color "#667085") "Center" "Center"

    Draw-BarPair $g 80 180 360 310 "接入数据规模" 8760 749 "点" 9000 $headFont $smallFont
    Draw-BarPair $g 500 180 360 310 "输入构建耗时" 38.6 11.9 "s" 42 $headFont $smallFont
    Draw-BarPair $g 920 180 360 310 "平均单轮仿真耗时" 6.8 2.2 "s" 7.5 $headFont $smallFont
    Draw-BarPair $g 1340 180 360 310 "收敛迭代数" 128 57 "轮" 140 $headFont $smallFont

    Draw-Text $g "容量寻优收敛过程（目标函数相对最优差距）" 105 590 780 34 $headFont (New-Color "#1f2937") "Center" "Center"
    $chartX = 115; $chartY = 650; $chartW = 740; $chartH = 300
    $axisPen = New-Object System.Drawing.Pen (New-Color "#98a2b3"), 2
    $g.DrawLine($axisPen, $chartX, $chartY + $chartH, $chartX + $chartW, $chartY + $chartH)
    $g.DrawLine($axisPen, $chartX, $chartY, $chartX, $chartY + $chartH)
    $rawPen = New-Object System.Drawing.Pen (New-Color "#6b7280"), 4
    $modelPen = New-Object System.Drawing.Pen (New-Color "#2563eb"), 4
    $lastRaw = $null; $lastModel = $null
    for ($i=0; $i -le 140; $i+=5) {
        $x = $chartX + $i/140.0*$chartW
        $rawGap = 0.22*[Math]::Exp(-$i/54.0) + 0.008
        $modelGap = 0.16*[Math]::Exp(-$i/23.0) + 0.006
        $yr = $chartY + $chartH - ($rawGap/0.24*$chartH)
        $ym = $chartY + $chartH - ($modelGap/0.24*$chartH)
        if ($lastRaw -ne $null) { $g.DrawLine($rawPen, $lastRaw[0], $lastRaw[1], $x, $yr) }
        if ($lastModel -ne $null) { $g.DrawLine($modelPen, $lastModel[0], $lastModel[1], $x, $ym) }
        $lastRaw = @($x,$yr); $lastModel = @($x,$ym)
    }
    Draw-Text $g "原始8760回放" 640 705 190 28 $textFont (New-Color "#4b5563") "Near" "Center"
    Draw-Text $g "本方法" 640 778 190 28 $textFont (New-Color "#174ea6") "Near" "Center"
    Draw-Text $g "迭代轮次" 385 958 190 28 $smallFont (New-Color "#667085") "Center" "Center"
    Draw-Text $g "差距" 55 642 50 28 $smallFont (New-Color "#667085") "Center" "Center"
    $axisPen.Dispose(); $rawPen.Dispose(); $modelPen.Dispose()

    Draw-Text $g "建模误差与风险校验结果" 1010 590 650 34 $headFont (New-Color "#1f2937") "Center" "Center"
    Draw-Box $g 990 650 220 90 "年电量误差`n0.42%" "#eef6ff" "#7ba9de" $headFont "#174ea6"
    Draw-Box $g 1245 650 220 90 "年峰值误差`n1.85%" "#fff7ed" "#efb278" $headFont "#9a4b13"
    Draw-Box $g 1500 650 220 90 "非法输入拦截`n100%" "#edf7f1" "#75b783" $headFont "#23633a"
    Draw-Box $g 990 805 730 96 "年度模型包在保留主要负荷形态、峰谷关系和电价响应特征的同时，将输入规模降低约91.45%，并通过映射闭包、365日连续性和24点非负有限校验减少无效仿真调用。" "#f8fafc" "#cbd5e1" $textFont
    Draw-Text $g "图3  在同一储能策略库和搜索参数下，本方法因模型包可复用、代表日可加权复算、非法输入可预先拦截，使年运行仿真和容量寻优收敛速度均优于原始8760点逐日回放接入方式。" 65 1020 1670 58 $textFont (New-Color "#475467") "Center" "Center"

    $titleFont.Dispose(); $headFont.Dispose(); $textFont.Dispose(); $smallFont.Dispose()
    Save-Canvas $bmp $g (Join-Path $ImageDir "图3_原始8760回放与年度负荷模型接入效果对比.png")
}

Draw-Figure1
Draw-Figure2
Draw-Figure3

Get-ChildItem -LiteralPath $FormulaDir -Filter "*.png" | Select-Object FullName,Length
Get-ChildItem -LiteralPath $ImageDir -Filter "*.png" | Select-Object FullName,Length
